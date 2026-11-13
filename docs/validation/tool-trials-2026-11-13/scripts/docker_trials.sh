#!/usr/bin/env bash
. "$(dirname "$0")/common.sh"; cd "$LAB/trials"
( docker run --rm --name hms-lab-mcu --cpus 2 -v "$LAB/trials/mcu_inner.sh:/mcu_inner.sh:ro" ubuntu:24.04 bash /mcu_inner.sh > "$LAB/results/mcu_simavr.txt" 2> "$LAB/logs/mcu_simavr.log"; echo "mcu_simavr exit=$?" ) &
( docker run --rm --name hms-lab-ros --cpus 2 ros:jazzy-ros-base bash -c '
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq ros-jazzy-action-tutorials-cpp ros-jazzy-action-tutorials-interfaces >/dev/null 2>&1
  source /opt/ros/jazzy/setup.bash; echo "ROS_DISTRO=$ROS_DISTRO"
  (ros2 run action_tutorials_cpp fibonacci_action_server >/dev/null 2>&1 &) ; sleep 3
  timeout 30 ros2 action send_goal --feedback /fibonacci action_tutorials_interfaces/action/Fibonacci "{order: 5}" 2>&1 | tail -12
' > "$LAB/results/ros2_action.txt" 2> "$LAB/logs/ros2_action.log"; echo "ros2_action exit=$?" ) &
( cd "$LAB/cache" && [ -x renode/renode ] || { curl -fsSL -m 300 -o renode.tgz https://builds.renode.io/renode-latest.linux-portable.tar.gz && mkdir -p renode && tar xzf renode.tgz -C renode --strip-components=1 && rm renode.tgz; }
  { "$LAB/cache/renode/renode" --version 2>&1 | head -3
    timeout 60 "$LAB/cache/renode/renode" --disable-xwt --console --plain -e "mach create; machine LoadPlatformDescription @platforms/cpus/stm32f103.repl; machine; cpu; quit" 2>&1 | tail -8; } > "$LAB/results/renode.txt" 2> "$LAB/logs/renode.log"; echo "renode exit=$?" ) &
wait; echo ALL_DOCKER_TRIALS_DONE
