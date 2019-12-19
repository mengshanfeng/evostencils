import random
from inspect import isclass
import deap.gp


def generate(pset, min_height, max_height, condition, type_=None):
    """Generate a Tree as a list of list. The tree is build
    from the root to the leaves, and it stop growing when the
    condition is fulfilled.

    :param pset: Primitive set from which primitives are selected.
    :param min_height: Minimum height of the produced trees.
    :param max_height: Maximum Height of the produced trees.
    :param condition: The condition is a function that takes two arguments,
                      the height of the tree to build and the current
                      depth in the tree.
    :param type_: The type that should return the tree when called, when
                  :obj:`None` (default) the type of :pset: (pset.ret)
                  is assumed.
    :returns: A grown tree with leaves at possibly different depths
              depending on the condition function.
    """
    if type_ is None:
        type_ = pset.ret
    expression = []
    height = random.randint(min_height, max_height)
    stack = [(0, type_)]
    while len(stack) != 0:
        depth, type_ = stack.pop()
        is_primitive = True
        terminals_available = len(pset.terminals[type_]) > 0
        primitives_available = len(pset.primitives[type_]) > 0
        if condition(height, depth):
            if terminals_available:
                nodes = pset.terminals[type_]
                is_primitive = False
            elif primitives_available:
                nodes = pset.primitives[type_]
            else:
                raise RuntimeError(f"Neither terminal nor primitive available for {type_}")
        else:
            if primitives_available:
                nodes = pset.primitives[type_]
            elif terminals_available:
                nodes = pset.terminals[type_]
                is_primitive = False
            else:
                raise RuntimeError(f"Neither terminal nor primitive available for {type_}")
        choice = random.choice(nodes)
        if is_primitive:
            for arg in reversed(choice.args):
                stack.append((depth + 1, arg))
        else:
            if isclass(choice):
                choice = choice()
        expression.append(choice)
    return expression


def genGrow(pset, min_height, max_height, type_=None):
    def condition(height, depth):
        return depth >= height or \
           (depth >= min_height and random.random() < pset.terminalRatio)
    return generate(pset, min_height, max_height, condition, type_)


class PrimitiveSetTyped(deap.gp.PrimitiveSetTyped):

    def _add(self, prim):
        def addType(dict_, ret_type):
            if ret_type not in dict_:
                new_list = []
                for type_, list_ in dict_.items():
                    if ret_type.issubtype(type_):
                        for item in list_:
                            if item not in new_list:
                                new_list.append(item)
                dict_[ret_type] = new_list

        addType(self.primitives, prim.ret)
        addType(self.terminals, prim.ret)

        self.mapping[prim.name] = prim
        if isinstance(prim, deap.gp.Primitive):
            for type_ in prim.args:
                addType(self.primitives, type_)
                addType(self.terminals, type_)
            dict_ = self.primitives
        else:
            dict_ = self.terminals

        for type_ in dict_:
            if type_.issubtype(prim.ret):
                dict_[type_].append(prim)


def mutNodeReplacement(individual, pset):
    """Replaces a randomly chosen primitive from *individual* by a randomly
    chosen primitive with the same number of arguments from the :attr:`pset`
    attribute of the individual.
    :param individual: The normal or typed tree to be mutated.
    :returns: A tuple of one tree.
    """
    if len(individual) < 2:
        return individual,

    while True:
        index = random.randrange(1, len(individual))
        node = individual[index]

        if node.arity == 0:  # Terminal
            term = random.choice(pset.terminals[node.ret])
            if isclass(term):
                term = term()
            individual[index] = term
            return individual,
        else:  # Primitive
            prims = [p for p in pset.primitives[node.ret] if p.args == node.args]
            if len(prims) > 1:
                individual[index] = random.choice(prims)
                return individual,


def mutInsert(individual, min_height, max_height, pset):
    """Inserts a new branch at a random position in *individual*. The subtree
    at the chosen position is used as child node of the created subtree, in
    that way, it is really an insertion rather than a replacement. Note that
    the original subtree will become one of the children of the new subtree
    inserted, but not perforce the first (its position is randomly selected if
    the new primitive has more than one child).

    :param individual: The normal or typed tree to be mutated.
    :returns: A tuple of one tree.
    """
    index = random.randrange(len(individual))
    node = individual[index]
    slice_ = individual.searchSubtree(index)

    # As we want to keep the current node as children of the new one,
    # it must accept the return value of the current node

    def condition(height, depth):
        return depth >= height
    subtree = individual[slice_]
    new_subtree = generate_with_insertion(pset, min_height, max_height, condition, node.ret, subtree)
    individual[slice_] = new_subtree
    return individual,


def generate_with_insertion(pset, min_height, max_height, condition, return_type, subtree):
    expression = []
    height = random.randint(min_height, max_height)
    stack = [(0, return_type)]
    subtree_inserted = False
    while len(stack) != 0:
        depth, type_ = stack.pop()
        if not subtree_inserted and type_ == return_type and len(expression) > 0:
            expression.extend(subtree)
            subtree_inserted = True
            continue
        is_primitive = True
        terminals_available = len(pset.terminals[type_]) > 0
        primitives_available = len(pset.primitives[type_]) > 0
        if condition(height, depth):
            if terminals_available:
                nodes = pset.terminals[type_]
                is_primitive = False
            elif primitives_available:
                nodes = pset.primitives[type_]
            else:
                raise RuntimeError(f"Neither terminal nor primitive available for {type_}")
        else:
            if primitives_available:
                nodes = pset.primitives[type_]
            elif terminals_available:
                nodes = pset.terminals[type_]
                is_primitive = False
            else:
                raise RuntimeError(f"Neither terminal nor primitive available for {type_}")
        choice = random.choice(nodes)
        if is_primitive:
            for arg in reversed(choice.args):
                stack.append((depth + 1, arg))
        else:
            if isclass(choice):
                choice = choice()
        expression.append(choice)
    return expression