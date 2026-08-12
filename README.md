Uploading to BlueOS
=======
You need to add this yourself in the Settings in the manual extension tab

    {
      "ExposedPorts": {
        "8000/tcp": {}
      },
      "HostConfig": {
        "Privileged": true,
        "Binds": [
          "/usr/blueos/extensions/$IMAGE_NAME:/app",
          "/dev:/dev"
        ],
        "ExtraHosts": ["host.docker.internal:host-gateway"],
        "PortBindings": {
          "8000/tcp": [
            {
              "HostPort": ""
            }
          ]
        }
      }
    }
