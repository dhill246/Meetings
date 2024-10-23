from app import create_app, socketio
import logging

# Create the Flask app using the factory function
app = create_app()
app.debug = True  # Enable debug mode
logging.basicConfig(level=logging.DEBUG)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
