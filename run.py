import os
import staypresent

# Start the keep-alive web server
# It will read Render's assigned PORT automatically
port = int(os.getenv("PORT", 8080))

# Tell staypresent to run your bot file as a subprocess
# Note: It's running "main.py", which no longer contains staypresent code
staypresent.run("main.py", port=port)
