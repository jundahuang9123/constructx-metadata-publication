# UI Screenshot Capture

No fake screenshot is committed. Capture the real UI after the app is running and at least one catalog has been pushed.

1. Start Solid mode:

   ```bash
   SOLID_AUTH_MODE=trusted-header make up-solid
   ```

2. Push an example catalog with a WebID that is present in the configured registry.

3. Open `http://localhost:8000`.

4. Select the dataset so the detail panel and RDF graph are visible.

5. Save the screenshot as:

   ```text
   docs/img/ui-datasets.png
   ```

The top-level README is written to reference that path once the real image exists.

