#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <memory>
#include <cstring>

namespace py = pybind11;

class FastImagePublisher {
public:
    FastImagePublisher(const std::string& topic_name, const std::string& encoding = "mono8") {
        // Initialize rclcpp if not already initialized
        if (!rclcpp::ok()) {
            rclcpp::init(0, nullptr);
        }
        
        // Create a minimal node for publishing
        node_ = std::make_shared<rclcpp::Node>("fast_publisher_node");
        publisher_ = node_->create_publisher<sensor_msgs::msg::Image>(topic_name, 1);
        encoding_ = encoding;
    }

    void publish_image(
        py::array_t<uint8_t> numpy_array,
        int height,
        int width,
        int64_t sec,
        uint32_t nanosec,
        const std::string& frame_id
    ) {
        // Get numpy array info
        py::buffer_info buf = numpy_array.request();
        
        auto msg = std::make_unique<sensor_msgs::msg::Image>();
        
        // Set header
        msg->header.stamp.sec = sec;
        msg->header.stamp.nanosec = nanosec;
        msg->header.frame_id = frame_id;
        
        // Set image properties
        msg->height = height;
        msg->width = width;
        msg->encoding = encoding_;
        msg->is_bigendian = false;
        
        if (encoding_ == "mono8") {
            msg->step = width;
        } else if (encoding_ == "bgr8" || encoding_ == "rgb8") {
            msg->step = width * 3;
        }
        
        // Direct memory copy - this is the fast part!
        size_t data_size = buf.size;
        msg->data.resize(data_size);
        std::memcpy(msg->data.data(), buf.ptr, data_size);
        
        // Publish
        publisher_->publish(std::move(msg));
    }

    void publish_float32_image(
        py::array_t<float> numpy_array,
        int height,
        int width,
        int64_t sec,
        uint32_t nanosec,
        const std::string& frame_id
    ) {
        // Get numpy array info
        py::buffer_info buf = numpy_array.request();
        
        auto msg = std::make_unique<sensor_msgs::msg::Image>();
        
        // Set header
        msg->header.stamp.sec = sec;
        msg->header.stamp.nanosec = nanosec;
        msg->header.frame_id = frame_id;
        
        // Set image properties
        msg->height = height;
        msg->width = width;
        msg->encoding = "32FC1";
        msg->is_bigendian = false;
        msg->step = width * 4;  // 4 bytes per float32
        
        // Direct memory copy
        size_t data_size = buf.size * sizeof(float);
        msg->data.resize(data_size);
        std::memcpy(msg->data.data(), buf.ptr, data_size);
        
        // Publish
        publisher_->publish(std::move(msg));
    }

    size_t get_subscription_count() const {
        return publisher_->get_subscription_count();
    }

private:
    std::shared_ptr<rclcpp::Node> node_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr publisher_;
    std::string encoding_;
};

PYBIND11_MODULE(fast_publisher, m) {
    m.doc() = "Fast C++ publisher for numpy arrays to ROS2 Image messages";
    
    py::class_<FastImagePublisher>(m, "FastImagePublisher")
        .def(py::init<const std::string&, const std::string&>(),
             py::arg("topic_name"),
             py::arg("encoding") = "mono8")
        .def("publish_image", &FastImagePublisher::publish_image,
             py::arg("numpy_array"),
             py::arg("height"),
             py::arg("width"),
             py::arg("sec"),
             py::arg("nanosec"),
             py::arg("frame_id"),
             "Publish a numpy uint8 array as Image message")
        .def("publish_float32_image", &FastImagePublisher::publish_float32_image,
             py::arg("numpy_array"),
             py::arg("height"),
             py::arg("width"),
             py::arg("sec"),
             py::arg("nanosec"),
             py::arg("frame_id"),
             "Publish a numpy float32 array as 32FC1 Image message")
        .def("get_subscription_count", &FastImagePublisher::get_subscription_count,
             "Get number of subscribers to this topic");
}
