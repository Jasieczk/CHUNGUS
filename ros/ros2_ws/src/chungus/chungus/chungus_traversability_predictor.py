from array import array
import cv2
import datetime
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from torchvision import transforms
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, CompressedImage
from std_msgs.msg import Float32MultiArray, UInt8MultiArray

from chungus.networks import create_model
from chungus.chungus_backend import ChungusBackend

try:
    from chungus.fast_publisher import FastImagePublisher
    HAS_FAST_PUBLISHER = True
except ImportError:
    HAS_FAST_PUBLISHER = False

class ChungusTraversabilityPrediction(Node):

    def __init__(self):
        super().__init__('chungus_predictor_node')

        # -------------------------
        # Declare parameters
        # -------------------------
        self.declare_parameter('traversability_model_variant', 'dinov2featup_recons')
        self.declare_parameter('traversability_model_resx', 224)
        self.declare_parameter('traversability_model_resy', 224)

        self.declare_parameter('controller_paused_param', '/controller_paused')
        self.declare_parameter('controller_active_param', '/controller_active')
        self.declare_parameter('controller_paused', False)

        self.declare_parameter('retrain_on_start', False)
        self.declare_parameter('use_novelty_detection', True)
        self.declare_parameter('use_novelty_only_on_control_active', True)
        self.declare_parameter('novelty_stdevs', 2.0)

        self.declare_parameter('train_epochs', 50)
        self.declare_parameter('train_decay_gamma', 0.25)
        self.declare_parameter('train_decay_step', 50)
        self.declare_parameter('train_lr', 0.005)
        self.declare_parameter('train_wd', 0.0)
        self.declare_parameter('equality_threshold', 0.25)
        self.declare_parameter('lrizz_L', 0.5)

        self.declare_parameter('init_embeddings_file', '')
        self.declare_parameter('init_images_folder', '')
        self.declare_parameter('gen_results_folder', '')

        self.declare_parameter('camera_topic', '/camera/color/image')
        self.declare_parameter('use_compressed', False)

        self.declare_parameter('traversability_image_topic', '/chungus/traversability/prediction')
        self.declare_parameter('traversability_image_visualize_topic', '/chungus/traversability/visualization')
        self.declare_parameter('traversability_image_uncertainty_topic', '/chungus/traversability/uncertainty')

        # -------------------------
        # Read parameters
        # -------------------------
        self.model_variant = self.get_parameter('traversability_model_variant').value
        resx = self.get_parameter('traversability_model_resx').value
        resy = self.get_parameter('traversability_model_resy').value
        self.model_resolution = (resy, resx)

        # -------------------------
        # Model setup
        # -------------------------
        self.model = create_model(self.model_variant, output_size=self.model_resolution)

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required but not available")

        self.device = torch.device('cuda')
        self.model.to(self.device)
        self.model.eval()
        
        # Verify GPU is being used
        self.get_logger().info(f"Model on device: {next(self.model.parameters()).device}")
        self.get_logger().info(f"CUDA available: {torch.cuda.is_available()}, Device count: {torch.cuda.device_count()}")

        # -------------------------
        # Chungus backend
        # -------------------------
        self.run_id = f"run_{datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}"
        self.prediction_paused = False

        self.controller_paused_param = self.get_parameter('controller_paused_param').value
        self.controller_active_param = self.get_parameter('controller_active_param').value

        self.retrain_on_start = self.get_parameter('retrain_on_start').value
        self.use_novelty_detection = self.get_parameter('use_novelty_detection').value
        self.use_novelty_only_on_control_active = self.get_parameter(
            'use_novelty_only_on_control_active').value
        self.novelty_stdevs = self.get_parameter('novelty_stdevs').value

        self.initial_embeddings_file = Path(self.get_parameter('init_embeddings_file').value)
        self.initial_images_folder = Path(self.get_parameter('init_images_folder').value)
        self.results_folder = Path(self.get_parameter('gen_results_folder').value) / self.run_id

        self.chungus_backend = ChungusBackend(
            initial_embeddings_file=self.initial_embeddings_file,
            initial_images_folder=self.initial_images_folder,
            results_folder=self.results_folder,
            controller_paused_param=self.controller_paused_param,
            threshold_stdevs=self.novelty_stdevs,
            model_resolution=self.model_resolution,
            device=self.device,
            traversability_prediction_node=self,
            train_epochs=self.get_parameter('train_epochs').value,
            train_decay_gamma=self.get_parameter('train_decay_gamma').value,
            train_decay_step=self.get_parameter('train_decay_step').value,
            train_lr=self.get_parameter('train_lr').value,
            train_wd=self.get_parameter('train_wd').value,
            equality_threshold=self.get_parameter('equality_threshold').value,
            lrizz_L=self.get_parameter('lrizz_L').value
        )

        self.chungus_backend.pause_controller(False)

        # -------------------------
        # Publishers
        # -------------------------
        if HAS_FAST_PUBLISHER:
            # Use fast C++ publishers for all image topics
            self.traversability_pub = FastImagePublisher(
                self.get_parameter('traversability_image_topic').value,
                "mono8"
            )
            self.traversability_vis_pub = FastImagePublisher(
                self.get_parameter('traversability_image_visualize_topic').value,
                "bgr8"
            )
            self.traversability_uncertainty_pub = FastImagePublisher(
                self.get_parameter('traversability_image_uncertainty_topic').value,
                "32FC1"
            )
            self.get_logger().info("Using fast C++ publishers for all image topics")
        else:
            # Fallback to slow Python publishers
            self.traversability_pub = self.create_publisher(
                Image,
                self.get_parameter('traversability_image_topic').value,
                1
            )
            self.traversability_vis_pub = self.create_publisher(
                Image,
                self.get_parameter('traversability_image_visualize_topic').value,
                1
            )
            self.traversability_uncertainty_pub = self.create_publisher(
                Image,
                self.get_parameter('traversability_image_uncertainty_topic').value,
                1
            )
            self.get_logger().warn("Fast publisher not available, using slow Python publishers")
        
        # -------------------------
        # Subscriber
        # -------------------------
        self.camera_topic = self.get_parameter('camera_topic').value
        self.use_compressed = self.get_parameter('use_compressed').value

        if self.use_compressed:
            self.create_subscription(
                CompressedImage,
                self.camera_topic,
                self.image_callback,
                1
            )
        else:
            self.create_subscription(
                Image,
                self.camera_topic,
                self.image_callback,
                1
            )

        self.transform = transforms.Compose([transforms.ToTensor()])

        # -------------------------
        # Startup actions
        # -------------------------
        if self.retrain_on_start:
            self.get_logger().info("Retraining model...")
            self.prediction_paused = True
            self.chungus_backend.retrain_model()
            self.prediction_paused = False

        self.get_logger().info("Saving initial model...")
        self.prediction_paused = True
        self.chungus_backend.save_initial_model()
        self.prediction_paused = False

        self.get_logger().info("Chungus traversability predictor started")

    def update_model(self, state_dict):
        """ Update te state dict of the model """
        # Setup model
        self.model.update_model(state_dict)
        self.model.to(self.device)
        self.model.eval()

    def perform_inference(self, image, resize_features=False, compute_reconstruction=False):
        """ Perform inference on an image
        
        Predictions will be having the same shape (in H, W) as the original image, even if inference resolution was actually lower
        (i.e., will adaptively resize to accommodate model resolution and will resize back to accommodate original resolution)

        :param image: image to perform inference on
        :param resize_features: whether to resize features to original resolution (slow, only needed for relabeling)
        :param compute_reconstruction: whether to compute and resize reconstruction (slow, only needed if uncertainty is needed)
        :returns: dictionary containing keys 'prediction', 'prediction_raw', 'cls_token', 'reconstruction', and 'features'
        """

        # Perform inference
        ti0 = time.time()
        original_resolution = image.shape[:2][::-1] # will be (W,H)
        resized_image = cv2.resize(image, self.model_resolution[::-1], interpolation=cv2.INTER_LINEAR)
        ti1 = time.time()
        with torch.no_grad():
            network_output = self.model(self.transform(resized_image).float().to(self.device))
            ti2 = time.time()
            # Convert prediction to format expected
            prediction_raw = cv2.resize(network_output['prediction'].cpu().numpy(), original_resolution, interpolation=cv2.INTER_LINEAR) # prediction will be (H,W) - it has only 1 channel
            ti3 = time.time()
            prediction = np.clip(255 * prediction_raw, 0, 255)
            prediction = prediction.astype('uint8')

            if 'cls_token' in network_output:
                cls_token = network_output['cls_token'].cpu().numpy()
            else:
                cls_token = None

            # Only resize features if explicitly requested (e.g., during relabeling)
            if 'features' in network_output:
                if resize_features:
                    features = F.interpolate(network_output['features'].unsqueeze(0), size=original_resolution[::-1], mode='bilinear')[0].cpu().numpy()
                else:
                    features = None  # Skip expensive feature resizing for normal inference
            else:
                features = None

            # Only compute reconstruction if explicitly requested (e.g., when uncertainty topic has subscribers)
            if 'reconstruction' in network_output and compute_reconstruction:
                reconstruction = F.interpolate(network_output['reconstruction'].unsqueeze(0).unsqueeze(0), size=original_resolution[::-1], mode='bilinear')[0][0].cpu().numpy()
            else:
                reconstruction = None
        
        ti_end = time.time()
        # if not hasattr(self, '_inference_count'):
        #     self._inference_count = 0
        # self._inference_count += 1
        # if self._inference_count % 30 == 0:
        #     self.get_logger().info(
        #         f"Inference breakdown: resize_input={1000*(ti1-ti0):.1f}ms, "
        #         f"model={1000*(ti2-ti1):.1f}ms, "
        #         f"resize_pred={1000*(ti3-ti2):.1f}ms, "
        #         f"total_inference={1000*(ti_end-ti0):.1f}ms"
        #     )
        
        return {
            'prediction': prediction, # mono8 image with predictions (0-255 as uint8)
            'prediction_raw': prediction_raw, # this is the prediction that is still a float and is 0 (lowest trav) to 1 (highest trav)
            'reconstruction': reconstruction,
            'features': features,
            'cls_token': cls_token
        }
    
    def decode_image(self, camera_msg):
        """ Decodes an image from a message """

        if self.use_compressed:
            # Read compressed image
            image = cv2.cvtColor(cv2.imdecode(np.frombuffer(camera_msg.data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        else:
            # Read non-compressed image
            if camera_msg.is_bigendian:
                raise ValueError("Big endian image was received -- not implemented yet")
            
            W, H = camera_msg.width, camera_msg.height
            raw_image_data = np.frombuffer(camera_msg.data, np.uint8).reshape((H, W, -1))
            if camera_msg.encoding == 'bgr8':
                image = cv2.cvtColor(raw_image_data, cv2.COLOR_BGR2RGB)
            elif camera_msg.encoding == 'rgb8':
                image = raw_image_data
            elif camera_msg.encoding == 'bgra8':
                image = cv2.cvtColor(raw_image_data, cv2.COLOR_BGRA2RGB)
            elif camera_msg.encoding == 'rgba8':
                image = cv2.cvtColor(raw_image_data, cv2.COLOR_RGBA2RGB)
            else:
                raise ValueError("Traversability image generator does not support encoding '{}'".format(camera_msg.encoding))
        
        return image
    
    def publish_prediction(self, camera_msg, inference_results):
        """ Publishes a prediction using the provided inference results """
        tp0 = time.time()
        # Publish image
        # Note: prediction is (H,W)
        prediction = inference_results['prediction']
        
        # Check subscription counts first
        has_main_sub = self.traversability_pub.get_subscription_count() > 0
        has_vis_sub = self.traversability_vis_pub.get_subscription_count() > 0
        has_unc_sub = self.traversability_uncertainty_pub.get_subscription_count() > 0
        
        tp1 = time.time()

        # Always publish traversability prediction
        if HAS_FAST_PUBLISHER:
            # Fast C++ path - direct numpy to ROS2 Image message (< 1ms)
            self.traversability_pub.publish_image(
                prediction,
                prediction.shape[0],
                prediction.shape[1],
                camera_msg.header.stamp.sec,
                camera_msg.header.stamp.nanosec,
                camera_msg.header.frame_id
            )
        else:
            # Slow Python fallback (80ms+)
            msg_trav = Image()
            msg_trav.header.stamp = camera_msg.header.stamp
            msg_trav.header.frame_id = camera_msg.header.frame_id
            msg_trav.height = prediction.shape[0]
            msg_trav.width = prediction.shape[1]
            msg_trav.encoding = "mono8"
            msg_trav.is_bigendian = False
            msg_trav.step = prediction.shape[1]
            msg_trav.data = prediction.tobytes()
            self.traversability_pub.publish(msg_trav)
    
        tp2 = time.time()

        # Visualization - colormap is expensive, make it optional
        if has_vis_sub:
            if HAS_FAST_PUBLISHER:
                # Fast C++ path for colormap visualization
                colormap_image = cv2.applyColorMap(prediction, cv2.COLORMAP_JET)
                self.traversability_vis_pub.publish_image(
                    colormap_image,
                    prediction.shape[0],
                    prediction.shape[1],
                    camera_msg.header.stamp.sec,
                    camera_msg.header.stamp.nanosec,
                    camera_msg.header.frame_id
                )
            else:
                # Slow Python fallback
                msg_trav_vis = Image()
                msg_trav_vis.header.stamp = camera_msg.header.stamp
                msg_trav_vis.header.frame_id = camera_msg.header.frame_id
                msg_trav_vis.height = prediction.shape[0]
                msg_trav_vis.width = prediction.shape[1]
                msg_trav_vis.encoding = "bgr8"
                msg_trav_vis.is_bigendian = False
                msg_trav_vis.step = prediction.shape[1] * 3
                msg_trav_vis.data = cv2.applyColorMap(prediction, cv2.COLORMAP_JET).tobytes()
                self.traversability_vis_pub.publish(msg_trav_vis)

        tp3 = time.time()

        # Publish uncertainty image (if available) - also make optional
        uncertainty = inference_results['reconstruction']
        if uncertainty is not None and has_unc_sub:
            if HAS_FAST_PUBLISHER:
                # Fast C++ path for float32 uncertainty
                uncertainty_float32 = uncertainty.astype(np.float32)
                self.traversability_uncertainty_pub.publish_float32_image(
                    uncertainty_float32,
                    uncertainty.shape[0],
                    uncertainty.shape[1],
                    camera_msg.header.stamp.sec,
                    camera_msg.header.stamp.nanosec,
                    camera_msg.header.frame_id
                )
            else:
                # Slow Python fallback
                msg_trav_uncertainty = Image()
                msg_trav_uncertainty.header.stamp = camera_msg.header.stamp
                msg_trav_uncertainty.header.frame_id = camera_msg.header.frame_id
                msg_trav_uncertainty.height = uncertainty.shape[0]
                msg_trav_uncertainty.width = uncertainty.shape[1]
                msg_trav_uncertainty.encoding = "32FC1"
                msg_trav_uncertainty.is_bigendian = False
                msg_trav_uncertainty.step = uncertainty.shape[1] * 4
                msg_trav_uncertainty.data = uncertainty.astype(np.float32).tobytes()
                self.traversability_uncertainty_pub.publish(msg_trav_uncertainty)
        
        tp_end = time.time()
        # if not hasattr(self, '_pub_count'):
        #     self._pub_count = 0
        # self._pub_count += 1
        # if self._pub_count % 30 == 0:
        #     self.get_logger().info(
        #         f"Publish breakdown: check_subs={1000*(tp1-tp0):.1f}ms, "
        #         f"main={1000*(tp2-tp1):.1f}ms, "
        #         f"vis={1000*(tp3-tp2):.1f}ms, "
        #         f"total_pub={1000*(tp_end-tp0):.1f}ms "
        #         f"(subs: main={has_main_sub}, vis={has_vis_sub}, unc={has_unc_sub})"
        #     )
    
    def image_callback(self, camera_msg):
        """Callback for when images are received"""

        if self.prediction_paused:
            return

        t_start = time.time()
        #self.get_logger().info("Predicting an image")

        self.prediction_paused = True

        # --------------------------------
        # Controller active check
        # --------------------------------
        controller_active = False

        try:
            # ROS 2: no global param server
            # This assumes another node sets a PARAMETER on ITSELF,
            # so here we only read the *name* and then query via services if needed.
            #
            # If controller_active_param is just a topic/state, this must be refactored.
            controller_active = self.get_parameter_or(
                self.controller_active_param.strip('/'),
                False
            )
        except Exception:
            controller_active = False

        # --------------------------------
        # Decode + inference
        # --------------------------------
        t0 = time.time()
        image = self.decode_image(camera_msg)
        t1 = time.time()
        # Only compute reconstruction if someone is subscribed to uncertainty topic
        need_reconstruction = self.traversability_uncertainty_pub.get_subscription_count() > 0
        inference_results = self.perform_inference(image, compute_reconstruction=need_reconstruction)
        t2 = time.time()
        self.publish_prediction(camera_msg, inference_results)
        t3 = time.time()

        # --------------------------------
        # Novelty detection
        # --------------------------------
        should_provide_label = False

        if self.use_novelty_detection and (
            not self.use_novelty_only_on_control_active or controller_active
        ):
            novelty = self.chungus_backend.compute_novelty(inference_results)
            t4 = time.time()

            self.get_logger().info(
                f"Novelty measured: {novelty['novelty_score']:.3f}. "
                f"Is novel: {novelty['is_novel']} "
                f"(threshold = {self.chungus_backend.novelty_threshold:.3f})"
            )

            should_provide_label = novelty['is_novel']
        else:
            t4 = t3

        if should_provide_label:
            self.get_logger().info("Requesting a label from user")
            self.chungus_backend.relabel(image, inference_results)

        # t_end = time.time()
        # self.get_logger().info(
        #     f"TIMING: decode={1000*(t1-t0):.1f}ms, "
        #     f"inference={1000*(t2-t1):.1f}ms, "
        #     f"publish={1000*(t3-t2):.1f}ms, "
        #     f"novelty={1000*(t4-t3):.1f}ms, "
        #     f"TOTAL={1000*(t_end-t_start):.1f}ms"
        # )

        self.prediction_paused = False



def main(args=None):
    rclpy.init(args=args)
    node = ChungusTraversabilityPrediction()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()