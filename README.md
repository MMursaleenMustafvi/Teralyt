# Terralyt
## Geospatial Intelligence Platform for Housing Societies

Terralyt is a proposed web-based geospatial intelligence platform designed to help property buyers, investors, and overseas Pakistanis evaluate housing societies in Pakistan using satellite imagery, geospatial analysis, machine learning, and interactive 3D visualization.

The platform aims to transform satellite-derived data into meaningful insights about a housing society's current development, historical growth, and potential future trajectory. By combining geospatial analytics with an interactive map interface, Terralyt seeks to support more informed property evaluation without requiring users to visit a location physically.

## Project Overview

Traditional property evaluation often relies on static listings, photographs, word of mouth, and physical site visits. These approaches may not provide sufficient information about a housing society's actual development or its historical growth.

Terralyt addresses this challenge by integrating satellite imagery, geographic information systems (GIS), machine learning, and spatial data management into a unified platform.

The project is initially scoped around a single pilot housing society in Pakistan, with an emphasis on data traceability, transparent analysis, and clearly communicated forecasting uncertainty.

## Key Features

### 1. Society and Plot Search
- Search for housing societies and individual plots by name, plot number, or geographic coordinates.
- Locate matching results on the interactive map.
- Support location-based property exploration.

### 2. Interactive 3D Geospatial Visualization
- Explore housing societies through an interactive 3D map powered by CesiumJS.
- Visualize society boundaries, plot geometries, roads, terrain, and surrounding areas.
- Switch between available satellite, road, and analytical map layers.
- Navigate the map through zooming, panning, and rotation.

### 3. AI-Based Development Classification
- Classify a housing society or plot into Low, Medium, or High development categories.
- Analyze geospatial indicators derived from satellite imagery.
- Consider built-up percentage, vegetation indices, and proximity to roads and infrastructure.
- Present development classifications as analytical outputs rather than subjective assessments.

### 4. Historical Development Analysis
- Examine changes in development indicators over historical periods.
- Compare the development patterns of a housing society over time.
- Use satellite-derived information to understand observed development trends.

### 5. Five-Year Development Forecasting
- Project potential changes in development indicators over a five-year horizon.
- Present forecast results as model-generated estimates.
- Communicate uncertainty and limitations associated with the available historical data.

### 6. Plot Status and Information
- Display plot coordinates, boundaries, and relevant development information.
- Support plot statuses such as Available, Reserved, and Sold.
- Associate plot status information with its source and confidence level.
- Distinguish verified records from information that cannot be confirmed.

### 7. Role-Based Dashboards and Management
The proposed platform supports three primary user roles:

- **End Users:** Search societies and plots, explore 3D maps, and review development classifications, historical trends, and forecasts.
- **Society Heads:** Maintain society and plot records, update plot statuses, and manage society-related dashboard information.
- **System Administrators:** Manage user accounts, roles, system settings, dashboards, and data-source verification.

### 8. Data Traceability and Verification
- Track the sources and dates of relevant datasets.
- Maintain confidence information for plot records and analytical results.
- Support verification of satellite imagery, plot boundaries, and plot status records.
- Improve transparency and accountability throughout the analysis process.

## Technology Stack

The proposed system uses the following technologies:

| Technology | Purpose |
|---|---|
| React.js (Vite) | Frontend development and interactive user interfaces |
| three.js | Detailed 3D model of the society (plots, houses, facilities) |
| CesiumJS | Interactive 3D geospatial visualization |
| Python | Geospatial processing and machine learning |
| scikit-learn | Machine learning model development and evaluation |
| FastAPI | Backend API development and model-serving endpoints |
| PostgreSQL | Relational database management |
| PostGIS | Spatial data storage and geographic queries |
| Google Earth Engine | Satellite imagery processing and geospatial feature extraction |
| QGIS | GIS data preparation and spatial analysis |
| Git and GitHub | Version control and collaborative development |

## System Architecture

Terralyt is designed around the integration of frontend visualization, backend services, geospatial data processing, machine learning, and spatial database management.

The intended workflow is as follows:

1. The user searches for a housing society or plot.
2. The system identifies the relevant geographic location and associated records.
3. Satellite imagery and geospatial datasets are processed to derive development indicators.
4. Machine learning models analyze the extracted features to generate development classifications and forecasting estimates.
5. Spatial information and analytical results are made available through backend APIs and the spatial database.
6. The frontend presents the results through an interactive 3D map, plot information panels, dashboards, and historical trend visualizations.

## Data and Analytical Methodology

Terralyt is designed to use observable geospatial indicators rather than relying exclusively on manually supplied descriptions.

The planned analytical workflow includes:

- Satellite imagery acquisition and processing through Google Earth Engine.
- Preparation and analysis of geographic data using GIS tools.
- Extraction of built-up and vegetation-related indicators.
- Analysis of proximity to roads and infrastructure.
- Machine learning-based development classification.
- Historical trend analysis and five-year forecasting.
- Validation and documentation of data sources and model outputs.

The reliability of these analyses depends on data availability, imagery quality, model validation, and the accuracy of the underlying geographic records.

## Project Scope

The initial scope focuses on developing and evaluating the platform for one pilot housing society.

The broader system design includes society and plot search, interactive 3D visualization, development classification, historical analysis, forecasting, role-based dashboards, plot record management, and data-source verification.

The project is developed as a Final Year Project at the FAST School of Computing, National University of Computer and Emerging Sciences, Chiniot-Faisalabad, Pakistan.

## Important Considerations

- **Forecasts are estimates:** Five-year projections represent model-based estimates and are not guarantees of future development.
- **Plot status requires verification:** Available, Reserved, and Sold statuses must be supported by verified society, developer, or transaction records. They cannot be reliably inferred from satellite imagery alone.
- **Data quality matters:** The accuracy of development analysis depends on the quality and availability of satellite imagery and supporting datasets.
- **Initial coverage is limited:** The project is scoped around a single pilot housing society.
- **Technical requirements:** Interactive 3D visualization requires a WebGL-compatible browser and a stable internet connection. Access to Google Earth Engine and online map services may also require appropriate configuration and credentials.

## Getting Started

The front end is built and runs today; the backend (FastAPI, PostgreSQL/PostGIS) and the machine learning model are the next stage.

**Requirements:** Node.js 20 or newer (includes npm).

```bash
npm install          # once
npm run dev          # development server: open http://localhost:5173/
npm run build        # production build in dist/ (the site and its map data)
```

Pages: home `#/`, 3D map `#/map`, search `#/search`, plot details `#/plot/<id>`, trends `#/trends`, log in `#/login`. The End User, Society Head and System Administrator dashboards open after logging in; until the backend is connected, accounts and changes are kept in the browser and three demo accounts exist (`user@terralyt.pk`, `head@terralyt.pk`, `admin@terralyt.pk`, password `Terralyt@2026`).

**Optional:** a Cesium ion token for the Real-world map tab, in a file `.env.local`: `VITE_CESIUM_TOKEN=...`. Without it the tab uses OpenStreetMap tiles on flat ground.

**Live site:** https://tahasaleemsheikh.github.io/Teralyt/. Every push to `main` is built and published by `.github/workflows/deploy.yml`. In the repository settings, Pages must use the source "GitHub Actions".

**Map data:** `data/` is generated by the Python tools in `tools/`; it is already in the repository, so no Python is needed to run the site.

## Future Enhancements

Potential future extensions include:

- Expanding coverage to additional housing societies across Pakistan.
- Improving model performance through additional historical satellite data and validation.
- Enhancing forecasting methods and uncertainty estimation.
- Integrating additional verified property and infrastructure datasets.
- Improving dashboard analytics and administrative reporting.
- Supporting broader deployment and scalability requirements.

## Academic Information

**Project Title:** Terralyt — Geospatial Intelligence Platform for Housing Societies

**Project Type:** Final Year Project

**Institution:** FAST School of Computing, National University of Computer and Emerging Sciences, Chiniot-Faisalabad, Pakistan

**Supervisor:** Ms. Mahzaib Younas

### Project Team
- Muhammad Mursaleen Mustafvi
- Taha Saleem Sheikh
- Rahmeen Nasr

## Intellectual Property

This project is developed as an academic project. According to the project report's intellectual property declaration, Terralyt is the intellectual property of the National University of Computer and Emerging Sciences and is protected by applicable intellectual property laws. Permission from the university may be required for reuse, commercial adoption, or further product development.

## License

No open-source license is specified in the project documentation. Please refer to the applicable institutional intellectual property requirements before redistributing or reusing the project.

---

Terralyt aims to make housing society evaluation more transparent and data-driven by combining geospatial intelligence, satellite-derived evidence, machine learning, and interactive 3D visualization.
