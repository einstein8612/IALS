from flow.core.params import NetParams
from flow.networks.traffic_light_grid import TrafficLightGridNetwork
from flow.envs import TrafficLightGridBitmapEnv
from flow.core.params import TrafficLightParams
from flow.core.params import SumoParams, EnvParams, InitialConfig, NetParams, \
    InFlows, SumoCarFollowingParams
from flow.core.params import VehicleParams
from flow.envs.ring.accel import AccelEnv, ADDITIONAL_ENV_PARAMS
from flow.controllers import SimCarFollowingController, GridRouter
import numpy as np

V_ENTER = 15
INNER_LENGTH = 100
LONG_LENGTH = 100
SHORT_LENGTH = 100
N_ROWS = 1
N_COLUMNS = 1
NUM_CARS_LEFT = 0
NUM_CARS_RIGHT = 0
NUM_CARS_TOP = 0
NUM_CARS_BOT = 0
tot_cars = (NUM_CARS_LEFT + NUM_CARS_RIGHT) * N_COLUMNS \
           + (NUM_CARS_BOT + NUM_CARS_TOP) * N_ROWS
grid_array = {
    "short_length": SHORT_LENGTH,
    "inner_length": INNER_LENGTH,
    "long_length": LONG_LENGTH,
    "row_num": N_ROWS,
    "col_num": N_COLUMNS,
    "cars_left": NUM_CARS_LEFT,
    "cars_right": NUM_CARS_RIGHT,
    "cars_top": NUM_CARS_TOP,
    "cars_bot": NUM_CARS_BOT
}
speed_limit = 35
horizontal_lanes = 1
vertical_lanes = 1
traffic_lights = True
additional_env_params = {'target_velocity': 50,
                         'switch_time': 3.0,
                         'num_observed': 2,
                         'discrete': True,
                         'tl_type': 'actuated',
                         'tl_controlled': ['center0'],
                         'scale': 10}
horizon = 200

class PartialTraffic(TrafficLightGridBitmapEnv):
    """
    """
    def __init__(self, influence, seed):
        additional_net_params = {'grid_array': grid_array,
                                 'speed_limit': speed_limit,
                                 'horizontal_lanes': horizontal_lanes, 
                                 'vertical_lanes': vertical_lanes,
                                 'traffic_lights': True}
        net_params = NetParams(additional_params=additional_net_params)
        vehicles = VehicleParams()
        vehicles.add(veh_id='idm',
                     acceleration_controller=(SimCarFollowingController, {}),
                     car_following_params=SumoCarFollowingParams(
                        min_gap=2.5,
                        decel=7.5,  # avoid collisions at emergency stops
                        max_speed=V_ENTER,
                        speed_mode="all_checks",),
                    routing_controller=(GridRouter, {}),
                    num_vehicles=tot_cars)
        # initial_config, net_params = get_inflow_params(col_num=N_COLUMNS,
        #                                                row_num=N_ROWS,
        #                                                additional_net_params=additional_net_params)
        initial_config = InitialConfig(spacing='custom', lanes_distribution=float('inf'), shuffle=True)                                                       
        network = TrafficLightGridNetwork(name='grid', vehicles=vehicles, net_params=net_params, initial_config=initial_config)
        
        env_params = EnvParams(horizon=horizon, additional_params=additional_env_params)
        sim_params = SumoParams(render=False, restart_instance=True, sim_step=1, print_warnings=False, seed=seed)
        super().__init__(env_params, sim_params, network, simulator='traci')
        self.influence = influence
        

    # override
    def reset(self):
        probs = self.influence.predict(np.zeros(40))
        state = super().reset()
        node_edges = self.network.node_mapping[int(self.tl_controlled[0][-1])][1]
        self.veh_id = 0
        for i, edge in enumerate(node_edges):
            sample = np.random.uniform(0,1)
            if sample < probs[i]: 
                self.k.vehicle.add(veh_id='idm_' + str(self.veh_id), type_id='idm', 
                               edge=edge, lane='allowed', pos=6, speed=10)
                self.veh_id += 1
        observation = []
        infs = []
        for edge in range(len(node_edges)):
            observation.append(state[edge][:-1])
        observation.append(state[-1]) #  append traffic light info
        observation = np.concatenate(observation)
        self.dset = observation
        reward = 0
        done = False
        return observation, reward, done, infs, self.dset

    # override
    def step(self, rl_actions):
        probs = self.influence.predict(self.dset)
        node_edges = self.network.node_mapping[int(self.tl_controlled[0][-1])][1]
        for i, edge in enumerate(node_edges):
            sample = np.random.uniform(0,1)
            if sample < probs[i]:
                self.k.vehicle.add(veh_id='idm_' + str(self.veh_id), type_id='idm',
                                edge=edge, lane='allowed', pos=6, speed=10)
                self.veh_id += 1
        state, reward, done, _ = super().step(rl_actions)
        node_edges = self.network.node_mapping[int(self.tl_controlled[0][-1])][1]
        observation = []
        infs = []
        for edge in range(len(node_edges)):
            observation.append(state[edge][:-1])
            infs.append(state[edge][-1]) # last bit is influence source
        observation.append(state[-1]) #  append traffic light info again
        observation = np.concatenate(observation)
        infs = np.array(infs)
        self.dset = observation
        return observation, reward, done, infs, self.dset
    
    # override
    @property
    def observation_space(self):
        pass

    def load_influence_model(self):
        self.influence._load_model()