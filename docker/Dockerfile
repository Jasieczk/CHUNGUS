FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/miniconda3/bin:$PATH"
ENV TORCH_CUDA_ARCH_LIST="8.6"
ENV FORCE_CUDA=1

# -------------------------
# System + build tools
# -------------------------
RUN apt-get update && apt-get install -y \
    tzdata wget curl git gnupg2 lsb-release \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# Add ROS 2 repository
# -------------------------
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/ros2.list

# -------------------------
# ROS 2 + build tools
# -------------------------
RUN apt-get update && apt-get install -y \
    ros-humble-desktop \
    python3-colcon-common-extensions \
    python3-rosdep \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init && rosdep update

# -------------------------
# Install Miniconda
# -------------------------
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /root/miniconda3 && rm miniconda.sh

RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# -------------------------
# Create CHUNGUS environment
# -------------------------
RUN conda create -n chungus python=3.10 -y

# -------------------------
# CRITICAL FIXES START HERE
# -------------------------

# 1. Install PyTorch with CUDA 11.8 (Matches base image)
#    We install this FIRST to ensure it grabs the right CUDA libs
RUN /root/miniconda3/envs/chungus/bin/pip install \
    torch==2.0.1+cu118 \
    torchvision==0.15.2+cu118 \
    torchaudio==2.0.2 \
    --extra-index-url https://download.pytorch.org/whl/cu118

# 2. Install dependencies with version pins to prevent breaking changes
#    - numpy<2.0: Fixes the binary incompatibility crash
#    - setuptools<70.0.0: Fixes the 'pkg_resources' error for FeatUp
#    - colcon-common-extensions: Ensures 'colcon build' uses Conda Python
#    - faiss-cpu: Installed via pip to avoid MKL conflicts
RUN /root/miniconda3/envs/chungus/bin/pip install \
    "numpy<2.0" \
    "setuptools<70.0.0" \
    colcon-common-extensions \
    rospkg opencv-python scikit-learn scikit-image pandas jupyterlab faiss-cpu

# Cleanup conda cache
RUN conda clean -afy

# -------------------------
# FeatUp (CUDA extension builds here)
# -------------------------
RUN git clone https://github.com/andreschreiber/FeatUp-ROS.git /home/chungus/docker/dependencies/featup

# Build FeatUp
# We use --no-build-isolation so it sees our pinned NumPy and PyTorch
RUN /bin/bash -c "source /root/miniconda3/etc/profile.d/conda.sh && \
    conda activate chungus && \
    TORCH_CUDA_ARCH_LIST='8.6' FORCE_CUDA=1 \
    pip install --no-build-isolation -e /home/chungus/docker/dependencies/featup"

# Optional: preload torch hub cache
COPY ./dependencies/torch_cache/hub /root/.cache/torch/hub



# Shell setup
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "source /root/miniconda3/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate chungus" >> ~/.bashrc

RUN export ROS_DOMAIN_ID=100 && \
    echo "export ROS_DOMAIN_ID=100" >> ~/.bashrc

# 1. Instalacja podstawowych narzędzi i kluczy Clearpath
RUN apt-get update && apt-get install -y wget nano git iputils-ping && \
    wget -O - https://packages.clearpathrobotics.com/public.key | tee /etc/apt/keyrings/clearpath.asc > /dev/null && \
    sh -c 'echo "deb [signed-by=/etc/apt/keyrings/clearpath.asc] https://packages.clearpathrobotics.com/stable/ubuntu $(lsb_release -cs) main" > /etc/apt/sources.list.d/clearpath-latest.list'

# 2. Instalacja symulatora i narzędzi Clearpath
RUN apt-get update && apt-get install -y \
    ros-humble-clearpath-simulator \
    ros-humble-clearpath-generator-common \
    ros-humble-clearpath-config-live \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install pyyaml    
# Możesz też użyć COPY, jeśli masz własny plik: COPY robot.yaml /root/clearpath/robot.yaml
RUN mkdir -p /root/clearpath
COPY robot.yaml /root/clearpath/robot.yaml

# 4. Generowanie plików startowych i URDF (BARDZO WAŻNE: używamy bash, aby móc użyć 'source')
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    ros2 run clearpath_generator_common generate_bash -s /root/clearpath && \
    ros2 run clearpath_generator_common generate_description -s /root/clearpath"


#ENV JACKAL_URDF_EXTRAS=/home/chungus/ros/catkin_ws/src/chungus/urdf/jackal_realsense.urdf.xacro

ENTRYPOINT ["/home/chungus/docker/docker_startup.sh"]