"""UI HTML generation."""


def get_fallback_ui() -> str:
    """Get fallback UI HTML."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AURA Backend</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: system-ui, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; text-align: center; }
            .status { padding: 15px; margin: 20px 0; border-radius: 5px; }
            .success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
            .info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }
            a { color: #007bff; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1> AURA Backend Server</h1>
            <div class="status success"> Server is running</div>
            <div class="status info">
                <strong>API Endpoints:</strong><br>
                • <a href="/api/v1/docs">/api/v1/docs</a> - API Documentation<br>
                • <a href="/api/v1/health">/api/v1/health</a> - Health Check<br>
                • <a href="/api/v1/graph/info">/api/v1/graph/info</a> - Graph Info
            </div>
        </div>
    </body>
    </html>
    """
