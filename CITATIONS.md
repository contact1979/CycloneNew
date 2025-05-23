# Code Citations & Attributions

This document lists all third-party code, components, and libraries used in the HydroBot project, along with their respective licenses and attributions.

## Core Libraries & Dependencies

- **CCXT** - MIT License

  - Used for cryptocurrency exchange integrations
  - <https://github.com/ccxt/ccxt>

- **pandas-ta** - MIT License

  - Technical analysis calculations
  - <https://github.com/twopirllc/pandas-ta>

- **Streamlit** - Apache License 2.0

  - Dashboard interface
  - <https://github.com/streamlit/streamlit>

## GitHub Actions Workflow Components

### Python Setup and Testing

- Source: <https://github.com/tetframework/Tonnikala>
- License: Apache-2.0
- Components Used:
  - Python version matrix configuration
  - Poetry dependency management
  - Test workflow structure

### Docker Build and Push Configuration

- Source: <https://github.com/jongwooo/blog>
- License: MIT
- Components Used:
  - Docker Buildx setup
  - Multi-platform build configuration
  - Image push workflow

### Container Registry Authentication

- Source: <https://github.com/fluxcd/website>
- License: Apache-2.0
- Components Used:
  - DockerHub login action
  - Container registry integration
  - Image tagging strategy

### Multi-Platform Build Support

- Source: <https://github.com/davetang/learning_docker>
- License: MIT
- Components Used:
  - QEMU setup
  - Cross-platform build flags

## Architecture & Design Patterns

The project's architecture draws inspiration from:

- **Event-driven architecture patterns** described in "Clean Architecture" by Robert C. Martin
- **Async Python patterns** from "Python Concurrency with asyncio" by Matthew Fowler
- **Trading system design patterns** from "Building Algorithmic Trading Systems" by Kevin Davey

## License Compliance

All code adaptations and usage comply with the original licenses.
This project itself is released under the MIT License.

See the [LICENSE](LICENSE) file for the complete license text.
