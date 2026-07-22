Uploading to BlueOS
=======
You need to add this yourself in the Settings in the manual extension tab

    {
      "ExposedPorts": {
        "8000/tcp": {}
      },
      "HostConfig": {
        "PortBindings": {
          "8000/tcp": [
            {
              "HostPort": ""
            }
          ]
        }
      }
    }
