import numpy as np

# from flatland.core.env import Environment
# from flatland.core.env_observation_builder import TreeObsForRailEnv

from flatland.core.transitions import Grid8Transitions, RailEnvTransitions
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.env_utils import distance_on_rail, connect_rail, get_direction, mirror
from flatland.envs.env_utils import get_rnd_agents_pos_tgt_dir_on_rail


def complex_rail_generator(nr_start_goal=1, min_dist=2, max_dist=99999, seed=0):
    """
    Parameters
    -------
    width : int
        The width (number of cells) of the grid to generate.
    height : int
        The height (number of cells) of the grid to generate.

    Returns
    -------
    numpy.ndarray of type numpy.uint16
        The matrix with the correct 16-bit bitmaps for each cell.
    """

    def generator(width, height, agents_handles, num_resets=0):
        rail_trans = RailEnvTransitions()
        grid_map = GridTransitionMap(width=width, height=height, transitions=rail_trans)
        rail_array = grid_map.grid
        rail_array.fill(0)

        np.random.seed(seed + num_resets)

        # generate rail array
        # step 1:
        # - generate a list of start and goal positions
        # - use a min/max distance allowed as input for this
        # - validate that start/goals are not placed too close to other start/goals
        #
        # step 2: (optional)
        # - place random elements on rails array
        #   - for instance "train station", etc.
        #
        # step 3:
        # - iterate over all [start, goal] pairs:
        #   - [first X pairs]
        #     - draw a rail from [start,goal]
        #     - draw either vertical or horizontal part first (randomly)
        #     - if rail crosses existing rail then validate new connection
        #       - if new connection is invalid turn 90 degrees to left/right
        #       - possibility that this fails to create a path to goal
        #         - on failure goto step1 and retry with seed+1
        #     - [avoid crossing other start,goal positions] (optional)
        #
        #   - [after X pairs]
        #     - find closest rail from start (Pa)
        #       - iterating outwards in a "circle" from start until an existing rail cell is hit
        #     - connect [start, Pa]
        #       - validate crossing rails
        #     - Do A* from Pa to find closest point on rail (Pb) to goal point
        #       - Basically normal A* but find point on rail which is closest to goal
        #       - since full path to goal is unlikely
        #     - connect [Pb, goal]
        #       - validate crossing rails
        #
        # step 4: (optional)
        # - add more rails to map randomly
        #
        # step 5:
        # - return transition map + list of [start, goal] points
        #

        start_goal = []
        start_dir = []
        nr_created = 0
        created_sanity = 0
        sanity_max = 9000
        while nr_created < nr_start_goal and created_sanity < sanity_max:
            all_ok = False
            for _ in range(sanity_max):
                start = (np.random.randint(0, width), np.random.randint(0, height))
                goal = (np.random.randint(0, height), np.random.randint(0, height))
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
                                    # print("too close:", dist, sg_new[i], sg[j])
                                    return False
                    return True

                if check_all_dist(sg_new):
                    all_ok = True
                    break

            if not all_ok:
                # we can might as well give up at this point
                # print("\n> Complex Rail Gen: Sanity counter reached, giving up!")
                break

            new_path = connect_rail(rail_trans, rail_array, start, goal)
            if len(new_path) >= 2:
                nr_created += 1
                # print(":::: path: ", new_path)
                start_goal.append([start, goal])
                start_dir.append(mirror(get_direction(new_path[0], new_path[1])))
            else:
                # after too many failures we will give up
                # print("failed...")
                created_sanity += 1

        print("\n> Complex Rail Gen: Created #", len(start_goal), "pairs")
        # print(start_goal)

        agents_position = [sg[0] for sg in start_goal]
        agents_target = [sg[1] for sg in start_goal]
        agents_direction = start_dir

        return grid_map, agents_position, agents_direction, agents_target

    return generator


def rail_from_manual_specifications_generator(rail_spec):
    """
    Utility to convert a rail given by manual specification as a map of tuples
    (cell_type, rotation), to a transition map with the correct 16-bit
    transitions specifications.

    Parameters
    -------
    rail_spec : list of list of tuples
        List (rows) of lists (columns) of tuples, each specifying a cell for
        the RailEnv environment as (cell_type, rotation), with rotation being
        clock-wise and in [0, 90, 180, 270].

    Returns
    -------
    function
        Generator function that always returns a GridTransitionMap object with
        the matrix of correct 16-bit bitmaps for each cell.
    """

    def generator(width, height, agents_handles, num_resets=0):
        t_utils = RailEnvTransitions()

        height = len(rail_spec)
        width = len(rail_spec[0])
        rail = GridTransitionMap(width=width, height=height, transitions=t_utils)

        for r in range(height):
            for c in range(width):
                cell = rail_spec[r][c]
                if cell[0] < 0 or cell[0] >= len(t_utils.transitions):
                    print("ERROR - invalid cell type=", cell[0])
                    return []
                rail.set_transitions((r, c), t_utils.rotate_transition(t_utils.transitions[cell[0]], cell[1]))

        agents_position, agents_direction, agents_target = get_rnd_agents_pos_tgt_dir_on_rail(
            rail,
            len(agents_handles))

        return rail, agents_position, agents_direction, agents_target

    return generator


def rail_from_GridTransitionMap_generator(rail_map):
    """
    Utility to convert a rail given by a GridTransitionMap map with the correct
    16-bit transitions specifications.

    Parameters
    -------
    rail_map : GridTransitionMap object
        GridTransitionMap object to return when the generator is called.

    Returns
    -------
    function
        Generator function that always returns the given `rail_map' object.
    """

    def generator(width, height, agents_handles, num_resets=0):
        agents_position, agents_direction, agents_target = get_rnd_agents_pos_tgt_dir_on_rail(
            rail_map,
            len(agents_handles))

        return rail_map, agents_position, agents_direction, agents_target

    return generator


def rail_from_list_of_saved_GridTransitionMap_generator(list_of_filenames):
    """
    Utility to sequentially and cyclically return GridTransitionMap-s from a list of files, on each environment reset.

    Parameters
    -------
    list_of_filenames : list
        List of filenames with the saved grids to load.

    Returns
    -------
    function
        Generator function that always returns the given `rail_map' object.
    """

    def generator(width, height, agents_handles, num_resets=0):
        t_utils = RailEnvTransitions()
        rail_map = GridTransitionMap(width=width, height=height, transitions=t_utils)
        rail_map.load_transition_map(list_of_filenames[num_resets % len(list_of_filenames)], override_gridsize=False)

        if rail_map.grid.dtype == np.uint64:
            rail_map.transitions = Grid8Transitions()

        agents_position, agents_direction, agents_target = get_rnd_agents_pos_tgt_dir_on_rail(
            rail_map,
            len(agents_handles))

        return rail_map, agents_position, agents_direction, agents_target

    return generator


"""
def generate_rail_from_list_of_manual_specifications(list_of_specifications)
    def generator(width, height, num_resets=0):
        return generate_rail_from_manual_specifications(list_of_specifications)

    return generator
"""


def random_rail_generator(cell_type_relative_proportion=[1.0] * 11):
    """
    Dummy random level generator:
    - fill in cells at random in [width-2, height-2]
    - keep filling cells in among the unfilled ones, such that all transitions
      are legit;  if no cell can be filled in without violating some
      transitions, pick one among those that can satisfy most transitions
      (1,2,3 or 4), and delete (+mark to be re-filled) the cells that were
      incompatible.
    - keep trying for a total number of insertions
      (e.g., (W-2)*(H-2)*MAX_REPETITIONS ); if no solution is found, empty the
      board and try again from scratch.
    - finally pad the border of the map with dead-ends to avoid border issues.

    Dead-ends are not allowed inside the grid, only at the border; however, if
    no cell type can be inserted in a given cell (because of the neighboring
    transitions), deadends are allowed if they solve the problem. This was
    found to turn most un-genereatable levels into valid ones.

    Parameters
    -------
    width : int
        The width (number of cells) of the grid to generate.
    height : int
        The height (number of cells) of the grid to generate.

    Returns
    -------
    numpy.ndarray of type numpy.uint16
        The matrix with the correct 16-bit bitmaps for each cell.
    """

    def generator(width, height, agents_handles, num_resets=0):
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
                # cell = random.sample(cells_to_fill, 1)[0]
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

        agents_position, agents_direction, agents_target = get_rnd_agents_pos_tgt_dir_on_rail(
            return_rail,
            len(agents_handles))

        return return_rail, agents_position, agents_direction, agents_target

    return generator