#!/usr/bin/env python
""" This node will publish waypoints from the car's current position
to some distance ahead with respective target speeds for each waypoint.
"""

import rospy

from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped
from styx_msgs.msg import Lane
#from styx_msgs.msg import Waypoint
#from styx_msgs.msg import TrafficLight
import waypoint_helper

SPEED_MPH = 10.0 #: Vehicle Speed limit in mph
MPH_TO_MPS = 0.44704
MAX_SPEED = SPEED_MPH * MPH_TO_MPS #: Vehicle speed limit in m/s
LOOKAHEAD_WPS = 200 #: Number of waypoints we will publish
STALE_TIME = 0.5 #: Time since that indicates it is relatively new data
MIN_DISTANCE = 22.0 #: Minimum distance from away from traffic light
DELTA_DISTANCE = 8.0 #: Buffer distance to give time to completely stop
STOPPED_DISTANCE = DELTA_DISTANCE + MIN_DISTANCE #: Meters from light where the car is stopped
SLOW_DISTANCE = SPEED_MPH ** 1.175 #: Distance amount where vehicle slows down
# NOTE: For SLOW_DISTANCE tweak coefficient as necessary
# > 1.175 for more gradual slowdown, < 1.175 for more abrupt stopping
MAX_DISTANCE = SLOW_DISTANCE + STOPPED_DISTANCE #: Maximum distance from the traffic light to stop

class WaypointUpdater(object):
    """Given the position and map this object publishes
       points with target velocities representing path ahead"""

    def __init__(self):
        """Initialize Waypoint Updater"""

        rospy.init_node('waypoint_updater')
        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb, queue_size=1)
        rospy.Subscriber('/base_waypoints', Lane, self.base_waypoints_cb, queue_size=1)
        rospy.Subscriber('/traffic_waypoint', Int32, self.traffic_cb)
        #rospy.Subscriber('/obstacle_waypoints', PoseStamped, self.obstacle_cb)

        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)
        self.car_index_pub = rospy.Publisher('car_index', Int32, queue_size=1)

        self.base_waypoints = None
        self.pose = None #: Current vehicle location + orientation
        self.frame_id = None
        self.previous_car_index = 0 #: Where in base waypoints list the car is
        self.traffic_index = -1 #: Where in base waypoints list the traffic light is
        self.traffic_time_received = rospy.get_time() #: When traffic light info was received

        self.loop()

    def loop(self):
        """ Publishes car index and subset of waypoints with target velocities """
        rate = rospy.Rate(10)

        while not rospy.is_shutdown():
            rate.sleep()

            if self.base_waypoints is None or self.pose is None or self.frame_id is None:
                continue

            # Where in base waypoints list the car is
            car_index = waypoint_helper.get_closest_waypoint_index(self.pose, self.base_waypoints)

            # Get subset waypoints ahead
            lookahead_waypoints = waypoint_helper.get_next_waypoints(self.base_waypoints,
                                                                     car_index, LOOKAHEAD_WPS)

            # Traffic light must be in front and not too far ahead and new
            is_new = rospy.get_time() - self.traffic_time_received < STALE_TIME
            is_near_ahead = False

            if (self.traffic_index - car_index) > 0:
                d = waypoint_helper.distance(self.base_waypoints, car_index, self.traffic_index)
                is_near_ahead = MIN_DISTANCE < d < MAX_DISTANCE

            # Set target speeds
            if not (is_near_ahead and is_new):
                # Go full speed if no red traffic light
                for waypoint in lookahead_waypoints:
                    waypoint.twist.twist.linear.x = MAX_SPEED
            else:
                # Slow down and stop
                for i, waypoint in enumerate(lookahead_waypoints):
                    _, waypoint.twist.twist.linear.x = self.get_distance_speed_tuple(car_index + i)

            # Publish
            lane = waypoint_helper.make_lane_object(self.frame_id, lookahead_waypoints)
            self.final_waypoints_pub.publish(lane)
            self.car_index_pub.publish(car_index)

    def pose_cb(self, msg):
        """ Update vehicle location """
        self.pose = msg.pose # store location (x, y)
        self.frame_id = msg.header.frame_id

    def base_waypoints_cb(self, msg):
        """ Store the given map """
        # msg: styx_msgs.msg.lane
        self.base_waypoints = msg.waypoints

    def traffic_cb(self, msg):
        """ Consider traffic light when setting waypoint velocity """
        self.traffic_index = msg.data
        self.traffic_time_received = rospy.get_time()

    def obstacle_cb(self, msg):
        # pylint: disable=no-self-use
        """ Consider obstacles when setting waypoint velocity"""
        pass

    def get_distance_speed_tuple(self, index):
        """ Return tuple of distance from traffic light
            and target speed for slowing down """
        d = waypoint_helper.distance(self.base_waypoints, index, self.traffic_index)
        speed = 0.0

        if d > STOPPED_DISTANCE:
            speed = (d - STOPPED_DISTANCE) / SLOW_DISTANCE * MAX_SPEED

        if d < STOPPED_DISTANCE and d > MIN_DISTANCE:
            speed = 0.0
        return d, speed

    def get_waypoint_velocity(self, waypoint):
        # pylint: disable=no-self-use
        """ Get velocity of a given waypoints """
        return waypoint.twist.twist.linear.x

    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
        # pylint: disable=no-self-use
        """ Set the velocity of a given waypoint """
        waypoints[waypoint].twist.twist.linear.x = velocity


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
