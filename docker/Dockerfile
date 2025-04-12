FROM nvidia/cudagl:11.4.2-devel-ubuntu20.04
 
# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Preconfigure tzdata
RUN echo "Etc/UTC" > /etc/timezone && \
    ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    apt-get update && apt-get install -y tzdata && \
    dpkg-reconfigure --frontend noninteractive tzdata

# Install Python
RUN apt-get update && apt-get install -y \
    python3.8 \
    python3-pip \
    git

# Install PyTorch
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install other Python packages
RUN pip3 install cupy-cuda11x scikit-learn

# Install ROS
RUN apt-key adv --keyserver 'hkp://keyserver.ubuntu.com:80' --recv-key C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654
RUN sh -c 'echo "deb http://packages.ros.org/ros/ubuntu focal main" > /etc/apt/sources.list.d/ros-latest.list'
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-noetic-desktop-full

# Install relevant ROS packages
RUN apt install -y ros-noetic-pybind11-catkin \
    libopencv-dev \
    libeigen3-dev \
    libgmp-dev \
    libmpfr-dev \
    libboost-all-dev \
    ros-noetic-turtlebot3-gazebo ros-noetic-turtlebot3-teleop \
    ros-noetic-ros-numpy
RUN pip3 install catkin-tools

# Install Jackal and RealSense packages
RUN apt-get install -y ros-noetic-jackal-simulator ros-noetic-jackal-desktop ros-noetic-jackal-navigation
RUN apt-get install ros-noetic-realsense2-camera ros-noetic-realsense2-description ros-noetic-gazebo-plugins

# Install conda
RUN apt-get update
RUN apt-get install -y wget && rm -rf /var/lib/apt/lists/*
RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh 

# Create the environment for FeatUp using conda
RUN /root/miniconda3/bin/conda create -n chungus python=3.8.19 -y \
    && /root/miniconda3/bin/conda install -n chungus  pytorch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 pytorch-cuda=11.7 -c pytorch -c nvidia -y

# Install in conda environment what is needed to run in ros
RUN /root/miniconda3/envs/chungus/bin/pip install rospkg \
    && /root/miniconda3/envs/chungus/bin/pip install opencv-python

# Install Faiss
RUN /root/miniconda3/bin/conda install -n chungus -c conda-forge faiss-cpu -y

# Install dependencies for offline
RUN /root/miniconda3/bin/conda install -n chungus scikit-image pandas jupyterlab -y

# Add ROS to bashrc
RUN echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
# Add ROS workspace to bashrc
RUN echo "source /home/chungus/ros/catkin_ws/devel/setup.bash" >> ~/.bashrc
# Add Jackal URDF extra for camera
ENV JACKAL_URDF_EXTRAS=/home/chungus/ros/catkin_ws/src/chungus/urdf/jackal_realsense.urdf.xacro

# Add FeatUp (and cached weights)
RUN git clone https://github.com/andreschreiber/FeatUp-ROS.git /home/chungus/docker/dependencies/featup
RUN export TORCH_CUDA_ARCH_LIST="3.5;5.0;6.0;6.1;7.0;7.5;8.0;8.6+PTX" && /root/miniconda3/envs/chungus/bin/pip install -e /home/chungus/docker/dependencies/featup
COPY ./dependencies/torch_cache/hub /root/.cache/torch/hub

# Configure to always open in correct folder
RUN echo "cd /home/chungus" >> ~/.bashrc

ENTRYPOINT ["/home/chungus/docker/docker_startup.sh"]