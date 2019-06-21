import sys, os
from evostencils.code_generation.exastencils import ProgramGenerator


def main():
    if len(sys.argv[1:]) == 2 and os.path.exists(sys.argv[2]):
        problem_name = sys.argv[1]
        exastencils_path = sys.argv[2]
        dimensions = 2
        min_level = 2
        max_level = 10
        program_generator = ProgramGenerator(problem_name, exastencils_path,
                                             None, None, None, None, None, None, dimensions, None, min_level, max_level, None)
        time_to_solution, convergence_factor = program_generator.evaluate(number_of_samples=10)
        print(f'Time to solution: {time_to_solution} ms, Convergence Factor: {convergence_factor}')


if __name__ == "__main__":
    main()

