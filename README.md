NYC 311 Road Surface Complaint Data

# Setup

## Dependencies

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

To install dependencies:

```bash
uv sync
```

## Environment Variables

Create a `.env` file in the project root with your Socrata API credentials:

```
SOCRATA_APP_TOKEN=your_app_token_here
SOCRATA_API_KEY_ID=your_api_key_id_here
SOCRATA_API_KEY_SECRET=your_api_key_secret_here
```

These credentials can be obtained from the [NYC Open Data portal](https://opendata.cityofnewyork.us/).