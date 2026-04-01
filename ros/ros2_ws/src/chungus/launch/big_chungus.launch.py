from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():

    # Launch arguments
    use_simple_controller = LaunchConfiguration('use_simple_controller')
    config_file = LaunchConfiguration('config_file')

    return LaunchDescription([

        # Args
        DeclareLaunchArgument(
            'use_simple_controller',
            default_value='true'
        ),

        DeclareLaunchArgument(
            'config_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('chungus'),
                'config',
                'big_chungus.yaml'
            ])
        ),

        # Use simulation time
        Node(
            package='chungus',
            executable='chungus_predictor_node',
            name='chungus_predictor_node',
            parameters=[
                {'use_sim_time': True},
                config_file
            ],
            output='screen'
        ),

        # Simple controller (conditional) - COMMENTED OUT - executable doesn't exist yet
        # Node(
        #     package='chungus',
        #     executable='simple_controller',
        #     name='simple_controller',
        #     condition=IfCondition(use_simple_controller),
        #     output='screen'
        # ),

        # Gazebo world publisher - COMMENTED OUT - executable doesn't exist yet
        # Node(
        #     package='chungus',
        #     executable='gazebo_world_publisher',
        #     name='gazebo_world_publisher',
        #     output='screen'
        # ),

        # RViz include - COMMENTED OUT - viz.launch.py doesn't exist yet
        # IncludeLaunchDescription(
        #     PythonLaunchDescriptionSource(
        #         PathJoinSubstitution([
        #             FindPackageShare('chungus'),
        #             'launch',
        #             'viz.launch.py'
        #         ])
        #     )
        # ),
    ])
