# Xtream Loader

Xtream Loader is a web application built with FastAPI that provides a user-friendly interface for browsing and accessing content from an Xtream API. It allows users to view live streams, series, and films, EPG (Electronic Program Guide) information and video ability to stream in browser.

## Features

- Browse live streams by category
- Display EPG information for live streams
- Load TV series and episodes
- View film collections
- Video playback for compatible content
- Caching api results to reduce calls on the xtream server, data will refresh every 24hrs
- User authentication and admin panel
- Tailwind CSS

## Prerequisites

- Python 3.7+
- pip (Python package manager)
- An active Xtream API account with valid credentials

## Installation

1. Clone the repository.

2. Create a virtual environment and activate it:

   ```
   python -m venv venv
   source venv/bin/activate
   ```

   Windows

   ```
   venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Configuration

1. Copy the `sample.env` file to `.env`:

   ```
   cp sample.env .env
   ```

2. Edit the `.env` file and fill in your Xtream API credentials:
   ```
   API_BASE_URL=your_api_base_url
   API_USERNAME=your_username
   API_PASSWORD=your_password
   SECRET_KEY=your-secret-key
   ```

## Setting up the Admin Account

1. Run the create_admin script to set up an admin account:

   ```
   python create_admin.py
   ```

## Usage

1. Start the FastAPI server:

   ```
   python main.py
   ```

2. Open a web browser and navigate to `http://localhost:8000`

3. Use the navigation menu to browse live streams, series, and films.
