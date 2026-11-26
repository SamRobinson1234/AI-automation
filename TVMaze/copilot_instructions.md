# Copilot instructions

- Build all applications in Python.
- Use test-driven development: write a failing test before implementing each behavior, then make it pass and refactor.
- Extract all application constants into a JSON file and load them from there.
- Implement strict type checking using Pylance.
- Configure the Python language server to enforce strict type checking.
- Ensure that all type hints are accurate and complete throughout the codebase.
- Use mypy or a similar tool to verify type correctness as part of the development workflow.
- Treat all type checking warnings and errors as blockers that must be resolved before merging code.
- Regularly review and update type hints to reflect any changes in the codebase.
- Ensure all new code includes appropriate type annotations from the outset.
- Log all application runs to a file named `runlog` in the TVMaze folder root.
