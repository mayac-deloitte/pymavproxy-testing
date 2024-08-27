### Method 1: Using Uvicorn with SSL/TLS on macOS

1. **Install Uvicorn:**

   If you haven't already, install Uvicorn using pip:

   ```bash
   pip install uvicorn
   ```

2. **Generate a Self-Signed SSL Certificate (for testing purposes):**

   You can use `openssl` (which comes pre-installed on macOS) to generate a self-signed certificate:

   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout privkey.pem -out fullchain.pem -days 365 -nodes
   ```

   Follow the prompts to set up your certificate details. This will create `privkey.pem` (private key) and `fullchain.pem` (certificate) in the current directory.

3. **Run Uvicorn with SSL/TLS:**

   Use the generated certificate and key to start Uvicorn:

   ```bash
   uvicorn myapp:app --host 0.0.0.0 --port 443 --ssl-keyfile=privkey.pem --ssl-certfile=fullchain.pem
   ```

   Replace `myapp:app` with the correct path to your FastAPI app.

### Method 2: Using Nginx as a Reverse Proxy on macOS

1. **Install Nginx:**

   You can install Nginx using Homebrew:

   ```bash
   brew install nginx
   ```

   Nginx will be installed in `/usr/local/etc/nginx/`.

2. **Generate or Obtain an SSL Certificate:**

   You can either generate a self-signed certificate as described above or obtain a real one if you have a domain name.

3. **Configure Nginx:**

   Edit the Nginx configuration file located at `/usr/local/etc/nginx/nginx.conf` or create a new server block in `/usr/local/etc/nginx/servers/`. Here’s a basic example:

   ```nginx
   server {
       listen 80;
       server_name localhost;  # Use your domain if you have one

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       listen 443 ssl;
       ssl_certificate /path/to/fullchain.pem;
       ssl_certificate_key /path/to/privkey.pem;
   }
   ```

   Replace `/path/to/` with the actual paths to your certificate and key files.

4. **Start Nginx:**

   Start or restart Nginx:

   ```bash
   sudo nginx -s reload
   ```

5. **Run Uvicorn without TLS:**

   Start your FastAPI app using Uvicorn on a non-TLS port:

   ```bash
   uvicorn myapp:app --host 127.0.0.1 --port 8000
   ```

### Testing

- **Self-Signed Certificates:** If you use a self-signed certificate, your browser will warn you that the connection is not secure. This is expected for self-signed certificates, and you can usually bypass the warning for testing purposes.
  
- **Real Certificates:** If you use a certificate from a trusted CA (e.g., Let’s Encrypt), you won’t encounter browser warnings.

### Conclusion

Both methods work on macOS, but using Nginx as a reverse proxy is more robust for production deployments. For local development or testing, Uvicorn with a self-signed certificate might be sufficient.