# blenderheadless

blenderheadless is a project for running Blender in headless (command-line) mode, typically for automated rendering, scripting, or server-side processing without a graphical interface.

## What We Do

This project enables users to:
- Run Blender scripts without a GUI
- Automate rendering tasks
- Integrate Blender into pipelines or backend services

## Setup

1. **Environment Configuration**
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env with your actual values
   nano .env
   ```

2. **Google Cloud Service Account** (for Google Drive integration)
   ```bash
   # Place your Google Cloud service account JSON file
   # This file contains credentials and must NOT be committed to Git
   cp path/to/your/service_account.json api/service_account.json
   ```

3. **Required Environment Variables**
   - `GOOGLE_SERVICE_ACCOUNT_B64`: Secure token for web interface authentication
   base64 -w 0 service_account.json

4. **Deployment**
   - For local development: `docker compose up`
   - For production: Deploy via Git (Coolify, etc.)


## How to Run

1. **Install Blender**

   Make sure Blender is installed on your system and accessible from the command line.

2. **Run a Script Headlessly**

   Use the following command to run Blender in headless mode with your script:

   ```sh
   blender --background --python your_script.py
   ```

   - `--background` runs Blender without the GUI.
   - `--python your_script.py` executes the specified Python script.

3. **Example**

   To render a scene from a `.blend` file:

   ```sh
   blender --background your_scene.blend --render-output //output --render-frame 1
   ```

   Replace `your_scene.blend` and `output` with your actual file and output path.

## More Information

See the [Blender command line documentation](https://docs.blender.org/manual/en/latest/advanced/command_line.html) for more options.