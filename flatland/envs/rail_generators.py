"""Rail generators (infrastructure manager, "Infrastrukturbetreiber")."""
import time
import warnings
from typing import Callable, Tuple, Optional, Dict, List, Any

import msgpack
import numpy as np

from flatland.core.grid.grid4_utils import get_direction, mirror
from flatland.core.grid.grid_utils import distance_on_rail, direction_to_point
from flatland.core.grid.rail_env_grid import RailEnvTransitions
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid4_generators_utils import connect_rail, connect_cities, connect_straigt_line

RailGeneratorProduct = Tuple[GridTransitionMap, Optional[Dict]]
RailGenerator = Callable[[int, int, int, int], RailGeneratorProduct]


def empty_rail_generator() -> RailGenerator:
    """
    Returns a generator which returns an empty rail mail with no agents.
    Primarily used by the editor
    """

    def generator(width: int, height: int, num_agents: int = 0, num_resets: int = 0) -> RailGeneratorProduct:
        rail_trans = RailEnvTransitions()
        grid_map = GridTransitionMap(width=width, height=height, transitions=rail_trans)
        rail_array = grid_map.grid
        rail_array.fill(0)

        return grid_map, None

    return generator


def complex_rail_generator(nr_start_goal=1,
                           nr_extra=100,
                           min_dist=20,
                           max_dist=99999,
                           seed=0) -> RailGenerator:
    """
    complex_rail_generator

    Parameters
    ----------
    width : int
        The width (number of cells) of the grid to generate.
    height : int
        The height (number of cells) of the grid to generate.

    Returns
    -------
    numpy.ndarray of type numpy.uint16
        The matrix with the correct 16-bit bitmaps for each cell.
    """

    def generator(width, height, num_agents, num_resets=0):

        if num_agents > nr_start_goal:
            num_agents = nr_start_goal
            print("complex_rail_generator: num_agents > nr_start_goal, changing num_agents")
        grid_map = GridTransitionMap(width=width, height=height, transitions=RailEnvTransitions())
        rail_array = grid_map.grid
        rail_array.fill(0)

        np.random.seed(seed + num_resets)

        # generate rail array
        # step 1:
        # - generate a start and goal position
        #   - validate min/max distance allowed
        #   - validate that start/goals are not placed too close to other start/goals
        #   - draw a rail from [start,goal]
        #     - if rail crosses existing rail then validate new connection
        #     - possibility that this fails to create a path to goal
        #     - on failure generate new start/goal
        #
        # step 2:
        # - add more rails to map randomly between cells that have rails
        #   - validate all new rails, on failure don't add new rails
        #
        # step 3:
        # - return transition map + list of [start_pos, start_dir, goal_pos] points
        #

        rail_trans = grid_map.transitions
        start_goal = []
        start_dir = []
        nr_created = 0
        created_sanity = 0
        sanity_max = 9000
        while nr_created < nr_start_goal and created_sanity < sanity_max:
            all_ok = False
            for _ in range(sanity_max):
                start = (np.random.randint(0, height), np.random.randint(0, width))
                goal = (np.random.randint(0, height), np.random.randint(0, width))

                # check to make sure start,goal pos is empty?
                if rail_array[goal] != 0 or rail_array[start] != 0:
                    continue
                # check min/max distance
                dist_sg = distance_on_rail(start, goal)
                if dist_sg < min_dist:
                    continue
                if dist_sg > max_dist:
                    continue
                # check distance to existing points
                sg_new = [start, goal]

                def check_all_dist(sg_new):
                    for sg in start_goal:
                        for i in range(2):
                            for j in range(2):
                                dist = distance_on_rail(sg_new[i], sg[j])
                                if dist < 2:
                                    return False
                    return True

                if check_all_dist(sg_new):
                    all_ok = True
                    break

            if not all_ok:
                # we might as well give up at this point
                break

            new_path = connect_rail(rail_trans, grid_map, start, goal)
            if len(new_path) >= 2:
                nr_created += 1
                start_goal.append([start, goal])
                start_dir.append(mirror(get_direction(new_path[0], new_path[1])))
            else:
                # after too many failures we will give up
                created_sanity += 1

        # add extra connections between existing rail
        created_sanity = 0
        nr_created = 0
        while nr_created < nr_extra and created_sanity < sanity_max:
            all_ok = False
            for _ in range(sanity_max):
                start = (np.random.randint(0, height), np.random.randint(0, width))
                goal = (np.random.randint(0, height), np.random.randint(0, width))
                # check to make sure start,goal pos are not empty
                if rail_array[goal] == 0 or rail_array[start] == 0:
                    continue
                else:
                    all_ok = True
                    break
            if not all_ok:
                break
            new_path = connect_rail(rail_trans, grid_map, start, goal)
            if len(new_path) >= 2:
                nr_created += 1

        return grid_map, {'agents_hints': {
            'start_goal': start_goal,
            'start_dir': start_dir
        }}

    return generator


def rail_from_manual_specifications_generator(rail_spec):
    """
    Utility to convert a rail given by manual specification as a map of tuples
    (cell_type, rotation), to a transition map with the correct 16-bit
    transitions specifications.

    Parameters
    ----------
    rail_spec : list of list of tuples
        List (rows) of lists (columns) of tuples, each specifying a rail_spec_of_cell for
        the RailEnv environment as (cell_type, rotation), with rotation being
        clock-wise and in [0, 90, 180, 270].

    Returns
    -------
    function
        Generator function that always returns a GridTransitionMap object with
        the matrix of correct 16-bit bitmaps for each rail_spec_of_cell.
    """

    def generator(width, height, num_agents, num_resets=0):
        rail_env_transitions = RailEnvTransitions()

        height = len(rail_spec)
        width = len(rail_spec[0])
        rail = GridTransitionMap(width=width, height=height, transitions=rail_env_transitions)

        for r in range(height):
            for c in range(width):
                rail_spec_of_cell = rail_spec[r][c]
                index_basic_type_of_cell_ = rail_spec_of_cell[0]
                rotation_cell_ = rail_spec_of_cell[1]
                if index_basic_type_of_cell_ < 0 or index_basic_type_of_cell_ >= len(rail_env_transitions.transitions):
                    print("ERROR - invalid rail_spec_of_cell type=", index_basic_type_of_cell_)
                    return []
                basic_type_of_cell_ = rail_env_transitions.transitions[index_basic_type_of_cell_]
                effective_transition_cell = rail_env_transitions.rotate_transition(basic_type_of_cell_, rotation_cell_)
                rail.set_transitions((r, c), effective_transition_cell)

        return [rail, None]

    return generator


def rail_from_file(filename, load_from_package=None) -> RailGenerator:
    """
    Utility to load pickle file

    Parameters
    ----------
    filename : Pickle file generated by env.save() or editor

    Returns
    -------
    function
        Generator function that always returns a GridTransitionMap object with
        the matrix of correct 16-bit bitmaps for each rail_spec_of_cell.
    """

    def generator(width, height, num_agents, num_resets):
        rail_env_transitions = RailEnvTransitions()
        if load_from_package is not None:
            from importlib_resources import read_binary
            load_data = read_binary(load_from_package, filename)
        else:
            with open(filename, "rb") as file_in:
                load_data = file_in.read()
        data = msgpack.unpackb(load_data, use_list=False)

        grid = np.array(data[b"grid"])
        rail = GridTransitionMap(width=np.shape(grid)[1], height=np.shape(grid)[0], transitions=rail_env_transitions)
        rail.grid = grid
        if b"distance_map" in data.keys():
            distance_map = data[b"distance_map"]
            if len(distance_map) > 0:
                return rail, {'distance_map': distance_map}
        return [rail, None]

    return generator


def rail_from_grid_transition_map(rail_map) -> RailGenerator:
    """
    Utility to convert a rail given by a GridTransitionMap map with the correct
    16-bit transitions specifications.

    Parameters
    ----------
    rail_map : GridTransitionMap object
        GridTransitionMap object to return when the generator is called.

    Returns
    -------
    function
        Generator function that always returns the given `rail_map` object.
    """

    def generator(width: int, height: int, num_agents: int, num_resets: int = 0) -> RailGeneratorProduct:
        return rail_map, None

    return generator


def random_rail_generator(cell_type_relative_proportion=[1.0] * 11) -> RailGenerator:
    """
    Dummy random level generator:
    - fill in cells at random in [width-2, height-2]
    - keep filling cells in among the unfilled ones, such that all transitions\
      are legit;  if no cell can be filled in without violating some\
      transitions, pick one among those that can satisfy most transitions\
      (1,2,3 or 4), and delete (+mark to be re-filled) the cells that were\
      incompatible.
    - keep trying for a total number of insertions\
      (e.g., (W-2)*(H-2)*MAX_REPETITIONS ); if no solution is found, empty the\
      board and try again from scratch.
    - finally pad the border of the map with dead-ends to avoid border issues.

    Dead-ends are not allowed inside the grid, only at the border; however, if
    no cell type can be inserted in a given cell (because of the neighboring
    transitions), deadends are allowed if they solve the problem. This was
    found to turn most un-genereatable levels into valid ones.

    Parameters
    ----------
    width : int
        The width (number of cells) of the grid to generate.
    height : int
        The height (number of cells) of the grid to generate.

    Returns
    -------
    numpy.ndarray of type numpy.uint16
        The matrix with the correct 16-bit bitmaps for each cell.
    """

    def generator(width: int, height: int, num_agents: int, num_resets: int = 0) -> RailGeneratorProduct:
        t_utils = RailEnvTransitions()

        transition_probability = cell_type_relative_proportion

        transitions_templates_ = []
        transition_probabilities = []
        for i in range(len(t_utils.transitions)):  # don't include dead-ends
            if t_utils.transitions[i] == int('0010000000000000', 2):
                continue

            all_transitions = 0
            for dir_ in range(4):
                trans = t_utils.get_transitions(t_utils.transitions[i], dir_)
                all_transitions |= (trans[0] << 3) | \
                                   (trans[1] << 2) | \
                                   (trans[2] << 1) | \
                                   (trans[3])

            template = [int(x) for x in bin(all_transitions)[2:]]
            template = [0] * (4 - len(template)) + template

            # add all rotations
            for rot in [0, 90, 180, 270]:
                transitions_templates_.append((template,
                                               t_utils.rotate_transition(
                                                   t_utils.transitions[i],
                                                   rot)))
                transition_probabilities.append(transition_probability[i])
                template = [template[-1]] + template[:-1]

        def get_matching_templates(template):
            ret = []
            for i in range(len(transitions_templates_)):
                is_match = True
                for j in range(4):
                    if template[j] >= 0 and template[j] != transitions_templates_[i][0][j]:
                        is_match = False
                        break
                if is_match:
                    ret.append((transitions_templates_[i][1], transition_probabilities[i]))
            return ret

        MAX_INSERTIONS = (width - 2) * (height - 2) * 10
        MAX_ATTEMPTS_FROM_SCRATCH = 10

        attempt_number = 0
        while attempt_number < MAX_ATTEMPTS_FROM_SCRATCH:
            cells_to_fill = []
            rail = []
            for r in range(height):
                rail.append([None] * width)
                if r > 0 and r < height - 1:
                    cells_to_fill = cells_to_fill + [(r, c) for c in range(1, width - 1)]

            num_insertions = 0
            while num_insertions < MAX_INSERTIONS and len(cells_to_fill) > 0:
                cell = cells_to_fill[np.random.choice(len(cells_to_fill), 1)[0]]
                cells_to_fill.remove(cell)
                row = cell[0]
                col = cell[1]

                # look at its neighbors and see what are the possible transitions
                # that can be chosen from, if any.
                valid_template = [-1, -1, -1, -1]

                for el in [(0, 2, (-1, 0)),
                           (1, 3, (0, 1)),
                           (2, 0, (1, 0)),
                           (3, 1, (0, -1))]:  # N, E, S, W
                    neigh_trans = rail[row + el[2][0]][col + el[2][1]]
                    if neigh_trans is not None:
                        # select transition coming from facing direction el[1] and
                        # moving to direction el[1]
                        max_bit = 0
                        for k in range(4):
                            max_bit |= t_utils.get_transition(neigh_trans, k, el[1])

                        if max_bit:
                            valid_template[el[0]] = 1
                        else:
                            valid_template[el[0]] = 0

                possible_cell_transitions = get_matching_templates(valid_template)

                if len(possible_cell_transitions) == 0:  # NO VALID TRANSITIONS
                    # no cell can be filled in without violating some transitions
                    # can a dead-end solve the problem?
                    if valid_template.count(1) == 1:
                        for k in range(4):
                            if valid_template[k] == 1:
                                rot = 0
                                if k == 0:
                                    rot = 180
                                elif k == 1:
                                    rot = 270
                                elif k == 2:
                                    rot = 0
                                elif k == 3:
                                    rot = 90

                                rail[row][col] = t_utils.rotate_transition(int('0010000000000000', 2), rot)
                                num_insertions += 1

                                break

                    else:
                        # can I get valid transitions by removing a single
                        # neighboring cell?
                        bestk = -1
                        besttrans = []
                        for k in range(4):
                            tmp_template = valid_template[:]
                            tmp_template[k] = -1
                            possible_cell_transitions = get_matching_templates(tmp_template)
                            if len(possible_cell_transitions) > len(besttrans):
                                besttrans = possible_cell_transitions
                                bestk = k

                        if bestk >= 0:
                            # Replace the corresponding cell with None, append it
                            # to cells to fill, fill in a transition in the current
                            # cell.
                            replace_row = row - 1
                            replace_col = col
                            if bestk == 1:
                                replace_row = row
                                replace_col = col + 1
                            elif bestk == 2:
                                replace_row = row + 1
                                replace_col = col
                            elif bestk == 3:
                                replace_row = row
                                replace_col = col - 1

                            cells_to_fill.append((replace_row, replace_col))
                            rail[replace_row][replace_col] = None

                            possible_transitions, possible_probabilities = zip(*besttrans)
                            possible_probabilities = [p / sum(possible_probabilities) for p in possible_probabilities]

                            rail[row][col] = np.random.choice(possible_transitions,
                                                              p=possible_probabilities)
                            num_insertions += 1

                        else:
                            print('WARNING: still nothing!')
                            rail[row][col] = int('0000000000000000', 2)
                            num_insertions += 1
                            pass

                else:
                    possible_transitions, possible_probabilities = zip(*possible_cell_transitions)
                    possible_probabilities = [p / sum(possible_probabilities) for p in possible_probabilities]

                    rail[row][col] = np.random.choice(possible_transitions,
                                                      p=possible_probabilities)
                    num_insertions += 1

            if num_insertions == MAX_INSERTIONS:
                # Failed to generate a valid level; try again for a number of times
                attempt_number += 1
            else:
                break

        if attempt_number == MAX_ATTEMPTS_FROM_SCRATCH:
            print('ERROR: failed to generate level')

        # Finally pad the border of the map with dead-ends to avoid border issues;
        # at most 1 transition in the neigh cell
        for r in range(height):
            # Check for transitions coming from [r][1] to WEST
            max_bit = 0
            neigh_trans = rail[r][1]
            if neigh_trans is not None:
                for k in range(4):
                    neigh_trans_from_direction = (neigh_trans >> ((3 - k) * 4)) & (2 ** 4 - 1)
                    max_bit = max_bit | (neigh_trans_from_direction & 1)
            if max_bit:
                rail[r][0] = t_utils.rotate_transition(int('0010000000000000', 2), 270)
            else:
                rail[r][0] = int('0000000000000000', 2)

            # Check for transitions coming from [r][-2] to EAST
            max_bit = 0
            neigh_trans = rail[r][-2]
            if neigh_trans is not None:
                for k in range(4):
                    neigh_trans_from_direction = (neigh_trans >> ((3 - k) * 4)) & (2 ** 4 - 1)
                    max_bit = max_bit | (neigh_trans_from_direction & (1 << 2))
            if max_bit:
                rail[r][-1] = t_utils.rotate_transition(int('0010000000000000', 2),
                                                        90)
            else:
                rail[r][-1] = int('0000000000000000', 2)

        for c in range(width):
            # Check for transitions coming from [1][c] to NORTH
            max_bit = 0
            neigh_trans = rail[1][c]
            if neigh_trans is not None:
                for k in range(4):
                    neigh_trans_from_direction = (neigh_trans >> ((3 - k) * 4)) & (2 ** 4 - 1)
                    max_bit = max_bit | (neigh_trans_from_direction & (1 << 3))
            if max_bit:
                rail[0][c] = int('0010000000000000', 2)
            else:
                rail[0][c] = int('0000000000000000', 2)

            # Check for transitions coming from [-2][c] to SOUTH
            max_bit = 0
            neigh_trans = rail[-2][c]
            if neigh_trans is not None:
                for k in range(4):
                    neigh_trans_from_direction = (neigh_trans >> ((3 - k) * 4)) & (2 ** 4 - 1)
                    max_bit = max_bit | (neigh_trans_from_direction & (1 << 1))
            if max_bit:
                rail[-1][c] = t_utils.rotate_transition(int('0010000000000000', 2), 180)
            else:
                rail[-1][c] = int('0000000000000000', 2)

        # For display only, wrong levels
        for r in range(height):
            for c in range(width):
                if rail[r][c] is None:
                    rail[r][c] = int('0000000000000000', 2)

        tmp_rail = np.asarray(rail, dtype=np.uint16)

        return_rail = GridTransitionMap(width=width, height=height, transitions=t_utils)
        return_rail.grid = tmp_rail

        return return_rail, None

    return generator


def sparse_rail_generator(num_cities=5, grid_mode=False, max_inter_city_rails=4, max_tracks_in_city=4,
                          seed=0) -> RailGenerator:
    """
    Generates railway networks with cities and inner city rails
    :param num_cities: Number of city centers in the map
    :param grid_mode: Arange cities in a grid or randomly
    :param max_inter_city_rails: Maximum number of connecting rails going out from a city
    :param max_tracks_in_city: maximum number of internal rails
    :param seed: Random seed to initiate rail
    :return: generator
    """

    def generator(width, height, num_agents, num_resets=0) -> RailGeneratorProduct:

        rail_trans = RailEnvTransitions()
        grid_map = GridTransitionMap(width=width, height=height, transitions=rail_trans)
        rail_array = grid_map.grid
        rail_array.fill(0)
        np.random.seed(seed + num_resets)
        node_radius = int(np.ceil((max_tracks_in_city + 2) / 2.0)) + 1
        max_inter_city_rails_allowed = max_inter_city_rails
        if max_inter_city_rails_allowed > max_tracks_in_city:
            max_inter_city_rails_allowed = max_tracks_in_city
        # Generate a set of nodes for the sparse network
        # Try to connect cities to nodes first
        city_positions = []
        intersection_positions = []

        # Evenly distribute cities and intersections
        node_time_start = time.time()
        node_positions: List[Any] = None
        nb_nodes = num_cities
        if grid_mode:
            node_positions, city_cells = _generate_node_positions_grid_mode(nb_nodes, node_radius, height, width)
        else:
            node_positions, city_cells = _generate_random_node_positions(nb_nodes, node_radius, height, width)

        # reduce nb_nodes, _num_cities, _num_intersections if less were generated in not_grid_mode
        nb_nodes = len(node_positions)
        print("City position time", time.time() - node_time_start, "Seconds")
        # Set up connection points for all cities
        node_connection_time = time.time()
        inner_connection_points, outer_connection_points, connection_info = _generate_node_connection_points(
            node_positions, node_radius, max_inter_city_rails_allowed,
            max_tracks_in_city)
        print("Connection points", time.time() - node_connection_time)

        # Connect the cities through the connection points
        city_connection_time = time.time()
        _connect_cities(node_positions, outer_connection_points, connection_info, city_cells, rail_trans, grid_map)
        print("City connection time", time.time() - city_connection_time)
        # Build inner cities
        city_build_time = time.time()
        through_tracks = _build_inner_cities(node_positions, inner_connection_points, outer_connection_points,
                                             node_radius,
                                             rail_trans,
                                             grid_map)
        print("City build time", time.time() - city_build_time)
        # Populate cities
        train_station_time = time.time()
        train_stations, built_num_trainstation = _set_trainstation_positions(node_positions, through_tracks,
                                                                             node_radius, grid_map)
        print("Trainstation placing time", time.time() - train_station_time)

        # Adjust the number of agents if you could not build enough trainstations
        if num_agents > built_num_trainstation:
            num_agents = built_num_trainstation
            warnings.warn("sparse_rail_generator: num_agents > nr_start_goal, changing num_agents")

        # Fix all transition elements
        grid_fix_time = time.time()
        _fix_transitions(city_cells, grid_map)
        print("Grid fix time", time.time() - grid_fix_time)

        # Generate start target pairs
        schedule_time = time.time()
        agent_start_targets_nodes, num_agents = _generate_start_target_pairs(num_agents, nb_nodes, train_stations)
        print("Schedule time", time.time() - schedule_time)
        return grid_map, {'agents_hints': {
            'num_agents': num_agents,
            'agent_start_targets_nodes': agent_start_targets_nodes,
            'train_stations': train_stations
        }}

    def _generate_random_node_positions(nb_nodes, node_radius, height, width):

        node_positions = []
        city_cells = []

        for node_idx in range(nb_nodes):
            to_close = True
            tries = 0

            while to_close:
                x_tmp = node_radius + 1 + np.random.randint(height - 2 * (node_radius + 1))
                y_tmp = node_radius + 1 + np.random.randint(width - 2 * (node_radius + 1))
                to_close = False
                # Check distance to nodes
                for node_pos in node_positions:
                    if _city_overlap((x_tmp, y_tmp), node_pos, 2 * (node_radius + 1) + 1):
                        to_close = True

                if not to_close:
                    node_positions.append((x_tmp, y_tmp))
                    city_cells.extend(_city_cells(node_positions[-1], node_radius))

                tries += 1
                if tries > 200:
                    warnings.warn(
                        "Could not only set {} nodes after {} tries, although {} of nodes required to be generated!".format(
                            len(node_positions),
                            tries, nb_nodes))
                    break

        return node_positions, city_cells

    def _generate_node_positions_grid_mode(nb_nodes, node_radius, height, width):
        nodes_ratio = height / width
        nodes_per_row = int(np.ceil(np.sqrt(nb_nodes * nodes_ratio)))
        nodes_per_col = int(np.ceil(nb_nodes / nodes_per_row))
        x_positions = np.linspace(node_radius + 1, height - node_radius - 2, nodes_per_row, dtype=int)
        y_positions = np.linspace(node_radius + 1, width - node_radius - 2, nodes_per_col, dtype=int)
        node_positions = []
        city_cells = []
        for node_idx in range(nb_nodes):
            x_tmp = x_positions[node_idx % nodes_per_row]
            y_tmp = y_positions[node_idx // nodes_per_row]
            node_positions.append((x_tmp, y_tmp))
            city_cells.extend(_city_cells(node_positions[-1], node_radius))
        return node_positions, city_cells

    def _generate_node_connection_points(node_positions, node_size, max_inter_city_rails_allowed, tracks_in_city=2):
        inner_connection_points = []
        outer_connection_points = []
        connection_info = []
        for node_position in node_positions:

            # Chose the directions where close cities are situated
            neighb_dist = []
            for neighb_node in node_positions:
                neighb_dist.append(distance_on_rail(node_position, neighb_node, metric="Manhattan"))
            closest_neighb_idx = argsort(neighb_dist)

            # Store the directions to these neighbours and orient city to face closest neighbour
            connection_sides_idx = []
            idx = 1
            current_closest_direction = direction_to_point(node_position, node_positions[closest_neighb_idx[idx]])
            connection_sides_idx.append(current_closest_direction)
            connection_sides_idx.append((current_closest_direction + 2) % 4)

            # set the number of tracks within a city, at least 2 tracks per city
            connections_per_direction = np.zeros(4, dtype=int)
            nr_of_connection_points = np.random.randint(2, tracks_in_city + 1)
            for idx in connection_sides_idx:
                connections_per_direction[idx] = nr_of_connection_points
            connection_points_coordinates_inner = [[] for i in range(4)]
            connection_points_coordinates_outer = [[] for i in range(4)]
            number_of_out_rails = np.random.randint(1, min(max_inter_city_rails_allowed, nr_of_connection_points) + 1)
            start_idx = int((nr_of_connection_points - number_of_out_rails) / 2)
            for direction in range(4):
                connection_slots = np.arange(connections_per_direction[direction]) - int(
                        connections_per_direction[direction] / 2)
                for connection_idx in range(connections_per_direction[direction]):
                    if direction == 0:
                        tmp_coordinates = (
                        node_position[0] - node_size, node_position[1] + connection_slots[connection_idx])
                    if direction == 1:
                        tmp_coordinates = (
                        node_position[0] + connection_slots[connection_idx], node_position[1] + node_size)
                    if direction == 2:
                        tmp_coordinates = (
                        node_position[0] + node_size, node_position[1] + connection_slots[connection_idx])
                    if direction == 3:
                        tmp_coordinates = (
                        node_position[0] + connection_slots[connection_idx], node_position[1] - node_size)
                    connection_points_coordinates_inner[direction].append(tmp_coordinates)
                    if connection_idx in range(start_idx, start_idx + number_of_out_rails + 1):
                        connection_points_coordinates_outer[direction].append(tmp_coordinates)

            inner_connection_points.append(connection_points_coordinates_inner)
            outer_connection_points.append(connection_points_coordinates_outer)
            connection_info.append(connections_per_direction)
        return inner_connection_points, outer_connection_points, connection_info

    def _connect_cities(node_positions, connection_points, connection_info, city_cells,
                        rail_trans, grid_map):
        """
        Function to connect the different cities through their connection points
        :param node_positions: Positions of city centers
        :param connection_points: Boarder connection points of cities
        :param connection_info: Number of connection points per direction NESW
        :param rail_trans: Transitions
        :param grid_map: Grid map
        :return:
        """
        for current_node in np.arange(len(node_positions)):
            direction = 0
            connected_to_city = []
            neighbours = _closest_neigh_in_direction(current_node, node_positions)
            for nbr_connection_points in connection_info[current_node]:
                if nbr_connection_points > 0:
                    neighb_idx = neighbours[direction]
                else:
                    direction += 1
                    continue

                # If no closest neighbour was found look at the neighbouring connections
                tmp_direction = (direction - 1) % 4
                while neighb_idx is None:
                    neighb_idx = neighbours[tmp_direction]
                    tmp_direction = (tmp_direction + 1) % 4

                connected_to_city.append(neighb_idx)
                for tmp_out_connection_point in connection_points[current_node][direction]:
                    # Find closest connection point
                    min_connection_dist = np.inf
                    all_neighb_connection_points = [item for sublist in connection_points[neighb_idx] for item in
                                                    sublist]

                    for tmp_in_connection_point in all_neighb_connection_points:
                        tmp_dist = distance_on_rail(tmp_out_connection_point, tmp_in_connection_point,
                                                    metric="Manhattan")
                        if tmp_dist < min_connection_dist:
                            min_connection_dist = tmp_dist
                            neighb_connection_point = tmp_in_connection_point
                    connect_cities(rail_trans, grid_map, tmp_out_connection_point, neighb_connection_point,
                                   city_cells)

                direction += 1
        return

    def _build_inner_cities(node_positions, inner_connection_points, outer_connection_points, node_radius, rail_trans,
                            grid_map):
        """
        Builds inner city tracks. This current version connects all incoming connections to all outgoing connections
        :param node_positions: Positions of the cities
        :param inner_connection_points: Points on city boarder that are used to generate inner city track
        :param outer_connection_points: Points where the city is connected to neighboring cities
        :param rail_trans:
        :param grid_map:
        :return: Returns the cells of the through path which cannot be occupied by trainstations
        """
        through_path_cells = [[] for i in range(len(node_positions))]
        for current_city in range(len(node_positions)):
            all_outer_connection_points = [item for sublist in outer_connection_points[current_city] for item in
                                           sublist]
            city_boarder = _city_boarder(node_positions[current_city], node_radius)

            # This part only works if we have keep same number of connection points for both directions
            # Also only works with two connection direction at each city
            for i in range(4):
                if len(inner_connection_points[current_city][i]) > 0:
                    boarder = i
                    break

            opposite_boarder = (boarder + 2) % 4
            boarder_one = inner_connection_points[current_city][boarder]
            boarder_two = inner_connection_points[current_city][opposite_boarder]

            # Connect the ends of the tracks
            connect_straigt_line(rail_trans, grid_map, boarder_one[0], boarder_one[-1], False)
            connect_straigt_line(rail_trans, grid_map, boarder_two[0], boarder_two[-1], False)

            # Connect parallel tracks
            for track_id in range(len(inner_connection_points[current_city][boarder])):
                if track_id % 2 == 0:
                    source = inner_connection_points[current_city][boarder][track_id]
                    target = inner_connection_points[current_city][opposite_boarder][track_id]
                    current_track = connect_straigt_line(rail_trans, grid_map, source, target)
                    if target in all_outer_connection_points and source in \
                        all_outer_connection_points and len(through_path_cells[current_city]) < 1:
                        through_path_cells[current_city].extend(current_track)
                else:
                    source = inner_connection_points[current_city][opposite_boarder][track_id]
                    target = inner_connection_points[current_city][boarder][track_id]

                    current_track = connect_straigt_line(rail_trans, grid_map, source, target)
                    if target in all_outer_connection_points and source in \
                        all_outer_connection_points and len(through_path_cells[current_city]) < 1:
                        through_path_cells[current_city].extend(current_track)

        return through_path_cells

    def _set_trainstation_positions(node_positions, through_tracks, node_radius, grid_map):
        """

        :param node_positions:
        :param num_trainstations:
        :return:
        """
        nb_nodes = len(node_positions)
        train_stations = [[] for i in range(nb_nodes)]
        built_num_trainstations = 0
        for current_city in range(len(node_positions)):
            for possible_location in _city_cells(node_positions[current_city], node_radius - 1):
                if possible_location in through_tracks[current_city]:
                    continue
                cell_type = grid_map.get_full_transitions(*possible_location)
                nbits = 0
                while cell_type > 0:
                    nbits += (cell_type & 1)
                    cell_type = cell_type >> 1
                if 1 <= nbits <= 2:
                    built_num_trainstations += 1
                    train_stations[current_city].append(possible_location)
        return train_stations, built_num_trainstations

    def _generate_start_target_pairs(num_agents, nb_nodes, train_stations):
        """
        Fill the trainstation positions with targets and goals
        :param num_agents:
        :param nb_nodes:
        :param train_stations:
        :return:
        """
        # Generate start and target node directory for all agents.
        # Assure that start and target are not in the same node
        agent_start_targets_nodes = []

        # Slot availability in node
        node_available_start = []
        node_available_target = []
        for node_idx in range(nb_nodes):
            node_available_start.append(len(train_stations[node_idx]))
            node_available_target.append(len(train_stations[node_idx]))

        # Assign agents to slots
        for agent_idx in range(num_agents):
            avail_start_nodes = [idx for idx, val in enumerate(node_available_start) if val > 0]
            avail_target_nodes = [idx for idx, val in enumerate(node_available_target) if val > 0]
            # Set probability to choose start and stop from trainstations
            sum_start = sum(np.array(node_available_start)[avail_start_nodes])
            sum_target = sum(np.array(node_available_target)[avail_target_nodes])
            p_avail_start = [float(i) / sum_start for i in np.array(node_available_start)[avail_start_nodes]]
            p_avail_target = [float(i) / sum_target for i in np.array(node_available_target)[avail_target_nodes]]

            start_node = np.random.choice(avail_start_nodes, p=p_avail_start)
            target_node = np.random.choice(avail_target_nodes, p=p_avail_target)
            tries = 0
            found_agent_pair = True
            while target_node == start_node:
                target_node = np.random.choice(avail_target_nodes)
                tries += 1
                # Test again with new start node if no pair is found (This code needs to be improved)
                if (tries + 1) % 10 == 0:
                    start_node = np.random.choice(avail_start_nodes)
                if tries > 100:
                    warnings.warn("Could not set trainstations, removing agent!")
                    found_agent_pair = False
                    break
            if found_agent_pair:
                node_available_start[start_node] -= 1
                node_available_target[target_node] -= 1
                agent_start_targets_nodes.append((start_node, target_node))
            else:
                num_agents -= 1
        return agent_start_targets_nodes, num_agents

    def _fix_transitions(city_cells, grid_map):
        """
        Function to fix all transition elements in environment
        """
        # Fix all nodes with illegal transition maps
        empty_to_fix = []
        rails_to_fix = []
        for cell in city_cells:
            check = grid_map.cell_neighbours_valid(cell, True)
            if grid_map.grid[cell] == int('1000010000100001', 2):
                grid_map.fix_transitions(cell)
            if not check:
                if grid_map.grid[cell] == 0:
                    empty_to_fix.append(cell)
                else:
                    rails_to_fix.append(cell)

        # Fix empty cells first to avoid cutting the network
        for cell in empty_to_fix:
            grid_map.fix_transitions(cell)

        # Fix all other cells
        for cell in rails_to_fix:
            grid_map.fix_transitions(cell)

    def _closest_neigh_in_direction(current_node, node_positions):
        """
        Returns indices of closest neighbours in every direction NESW
        :param current_node: Index of node in node_positions list
        :param node_positions: list of all points being considered
        :return: list of index of closest neighbours in all directions
        """
        node_dist = []
        closest_neighb = [None for i in range(4)]
        for av_node in range(len(node_positions)):
            node_dist.append(
                distance_on_rail(node_positions[current_node], node_positions[av_node], metric="Manhattan"))
        sorted_neighbours = np.argsort(node_dist)
        direction_set = 0
        for neighb in sorted_neighbours[1:]:
            direction_to_neighb = direction_to_point(node_positions[current_node], node_positions[neighb])
            if closest_neighb[direction_to_neighb] == None:
                closest_neighb[direction_to_neighb] = neighb
                direction_set += 1

            if direction_set == 4:
                return closest_neighb

        return closest_neighb

    def argsort(seq):
        # http://stackoverflow.com/questions/3071415/efficient-method-to-calculate-the-rank-vector-of-a-list-in-python
        return sorted(range(len(seq)), key=seq.__getitem__)

    def _city_cells(center, radius):
        """
        Function to return all cells within a city
        :param center: center coordinates of city
        :param radius: radius of city (it is a square)
        :return: returns flat list of all cell coordinates in the city
        """
        city_cells = []
        for x in range(-radius, radius + 1):
            for y in range(-radius, radius + 1):
                city_cells.append((center[0] + x, center[1] + y))

        return city_cells

    def _city_boarder(center, radius):
        city_boarder = []
        for x in range(-radius, radius + 1):
            for y in range(-radius, radius + 1):
                if abs(x) == radius or abs(y) == radius:
                    city_boarder.append((center[0] + x, center[1] + y))
        return city_boarder

    def _city_overlap(center_1, center_2, radius):
        return (np.abs(center_1[0] - center_2[0]) < radius and np.abs(center_1[1] - center_2[1]) < radius)

    return generator
