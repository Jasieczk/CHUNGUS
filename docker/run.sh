XAUTH=/tmp/.docker.xauth

echo "Preparing XAUTH data..."
xauth_list=$(xauth nlist :0 | tail -n 1 | sed -e 's/^..../ffff/')
if [ ! -f $XAUTH ]; then
    if [ ! -z "$xauth_list" ]; then
        echo $xauth_list | xauth -f $XAUTH nmerge -
    else
        touch $XAUTH
    fi
    chmod a+r $XAUTH
fi

echo "Done."
echo ""
echo "XAUTH file:"
file $XAUTH
echo "XAUTH permissions:"
ls -FAlh $XAUTH
echo "Launching Docker..."

docker run -it \
    --env="DISPLAY=$DISPLAY" \
    --env="QT_X11_NO_MITSHM=1" \
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
    --env="XAUTHORITY=$XAUTH" \
    --volume="$XAUTH:$XAUTH" \
    --net=host \
    --ulimit rtprio=99 \
    --cap-add=sys_nice \
    --privileged \
    -eHOST_USERNAME=$(whoami) \
    -v $pwd./../:/home/chungus/ \
    --gpus all \
    --name chungus \
    chungus_ros:latest \
    bash
