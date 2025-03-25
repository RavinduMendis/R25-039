## R25-039



## Setting Up the Virtual Environment

If you wish to set up a virtual environment for Python, follow these steps:

1. Create a virtual environment:
   ```bash
   python3 -m venv <name>
   ```

2. Activate the virtual environment:
   - For Linux:
     ```bash
     source <name>/bin/activate
     ```
   - For Windows: 
   
   ## karala baluwe nn na

    ```bash
     Navigate to the `Scripts` folder within the virtual environment and run the `activate` script.
     ```



## Libraries to Install

To install the required libraries for this project, run the following command:

```bash
pip install tensorflow numpy
```

```bash
# pip install colorama windows-curses
```



## Running the Program

To run the program, you will need two terminals or one terminal split into two sections.

### Server

1. Open the first terminal and navigate to the server directory:
   ```bash
   cd server
   ```

2. Run the server script:
   ```bash
   python server.py
   ```

### Client

1. Open the second terminal and navigate to the client directory:
   ```bash
   cd client
   ```

2. Run the client script:
   ```bash
   python client.py
   ```

### Adding New Clients

To add new clients:

1. Clone the client folder and rename it (e.g., `client2`, `client3`, etc.).

2. Navigate to the newly created client folder:
   ```bash
   cd client2
   ```

3. Modify the `client.py` script to ensure each client has a unique socket port number. For example, update the port for `client2`:
   ```python
   client_port = 6001  # Set a unique port for the client
   ```

4. Run the new client script:
   ```bash
   python client.py
   ```