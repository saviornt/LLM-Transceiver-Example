import asyncio
import websockets
import http.client
import json
import base64
import ssl
import os
import logging
from pydub import AudioSegment
import cv2
import numpy as np

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Client:
    def __init__(self):
        """
        Initialize the Client instance variables.
        """
        self.https_connection = None
        self.webrtc_connection = None
        self.is_webrtc_enabled = False

    async def connect_to_server(self, url, certfile=None):
        """
        Establish a connection to the server using HTTPS or WebRTC.

        Args:
            url (str): The server URL.
            certfile (str, optional): Path to SSL certificate file for secure WebSocket connection.
        """
        try:
            if not self.https_connection and not self.is_webrtc_enabled:
                self.https_connection = http.client.HTTPSConnection(url)
                logger.info(f"Connected to {url} using HTTPS")
            elif not self.is_webrtc_enabled:
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                if certfile:
                    ssl_context.load_verify_locations(certfile)
                self.webrtc_connection = await websockets.connect(f"wss://{url}/", ssl=ssl_context)
                self.is_webrtc_enabled = True
                logger.info(f"Connected to {url} using WebRTC")
        except Exception as e:
            logger.exception(f"Error connecting to server {url}: {e}")
            raise

    async def send_audio(self, audio_data):
        """
        Send audio data to the server.

        Args:
            audio_data (bytes): Raw audio data.
        """
        try:
            if self.https_connection:
                headers = {'Content-type': 'application/octet-stream'}
                self.https_connection.request('POST', '/audio', body=audio_data, headers=headers)
                response = self.https_connection.getresponse()
                logger.info(f"Sent audio data over HTTPS, response status: {response.status}")
                response.read()
            elif self.webrtc_connection:
                encoded_audio = base64.b64encode(audio_data).decode('utf-8')
                message = json.dumps({"type": "audio", "data": encoded_audio})
                await self.webrtc_connection.send(message)
                logger.info("Sent audio data over WebRTC")
        except Exception as e:
            logger.exception(f"Error sending audio data: {e}")

    async def receive_audio(self):
        """
        Receive audio data from the server.

        Returns:
            bytes: Received audio data.
        """
        try:
            if self.https_connection:
                self.https_connection.request('GET', '/audio')
                response = self.https_connection.getresponse()
                audio_data = response.read()
                logger.info("Received audio data over HTTPS")
                return audio_data
            elif self.webrtc_connection:
                while True:
                    message = await self.webrtc_connection.recv()
                    data = json.loads(message)
                    if data.get("type") == "audio":
                        decoded_audio = base64.b64decode(data.get("data"))
                        logger.info("Received audio data over WebRTC")
                        return decoded_audio
        except Exception as e:
            logger.exception(f"Error receiving audio data: {e}")
            return None

    async def send_video(self, frame):
        """
        Send video frame to the server.

        Args:
            frame (numpy.ndarray): Video frame.
        """
        try:
            _, encoded_image = cv2.imencode('.jpg', frame)
            image_bytes = encoded_image.tobytes()
            if self.https_connection:
                headers = {'Content-type': 'application/octet-stream'}
                self.https_connection.request('POST', '/video', body=image_bytes, headers=headers)
                response = self.https_connection.getresponse()
                logger.info(f"Sent video data over HTTPS, response status: {response.status}")
                response.read()
            elif self.webrtc_connection:
                encoded_video = base64.b64encode(image_bytes).decode('utf-8')
                message = json.dumps({"type": "video", "data": encoded_video})
                await self.webrtc_connection.send(message)
                logger.info("Sent video data over WebRTC")
        except Exception as e:
            logger.exception(f"Error sending video data: {e}")

    async def receive_video(self):
        """
        Receive video frame from the server.

        Returns:
            numpy.ndarray: Received video frame.
        """
        try:
            if self.https_connection:
                self.https_connection.request('GET', '/video')
                response = self.https_connection.getresponse()
                video_data = response.read()
                nparr = np.frombuffer(video_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                logger.info("Received video data over HTTPS")
                return frame
            elif self.webrtc_connection:
                while True:
                    message = await self.webrtc_connection.recv()
                    data = json.loads(message)
                    if data.get("type") == "video":
                        decoded_video = base64.b64decode(data.get("data"))
                        nparr = np.frombuffer(decoded_video, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        logger.info("Received video data over WebRTC")
                        return frame
        except Exception as e:
            logger.exception(f"Error receiving video data: {e}")
            return None

    async def send_text(self, text):
        """
        Send text message to the server.

        Args:
            text (str): Text message to send.
        """
        try:
            if self.https_connection:
                headers = {'Content-type': 'application/json'}
                body = json.dumps({"text": text})
                self.https_connection.request('POST', '/text', body=body, headers=headers)
                response = self.https_connection.getresponse()
                logger.info(f"Sent text data over HTTPS, response status: {response.status}")
                response.read()
            elif self.webrtc_connection:
                message = json.dumps({"type": "text", "data": text})
                await self.webrtc_connection.send(message)
                logger.info("Sent text data over WebRTC")
        except Exception as e:
            logger.exception(f"Error sending text data: {e}")

    async def receive_text(self):
        """
        Receive text message from the server.

        Returns:
            str: Received text message.
        """
        try:
            if self.https_connection:
                self.https_connection.request('GET', '/text')
                response = self.https_connection.getresponse()
                data = json.loads(response.read())
                text = data.get("text")
                logger.info("Received text data over HTTPS")
                return text
            elif self.webrtc_connection:
                while True:
                    message = await self.webrtc_connection.recv()
                    data = json.loads(message)
                    if data.get("type") == "text":
                        text = data.get("data")
                        logger.info("Received text data over WebRTC")
                        return text
        except Exception as e:
            logger.exception(f"Error receiving text data: {e}")
            return None

    async def send_image(self, image_path):
        """
        Send image to the server.

        Args:
            image_path (str): Path to the image file.
        """
        try:
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            if self.https_connection:
                headers = {'Content-type': 'application/octet-stream'}
                self.https_connection.request('POST', '/image', body=image_data, headers=headers)
                response = self.https_connection.getresponse()
                logger.info(f"Sent image data over HTTPS, response status: {response.status}")
                response.read()
            elif self.webrtc_connection:
                encoded_image = base64.b64encode(image_data).decode('utf-8')
                message = json.dumps({"type": "image", "data": encoded_image})
                await self.webrtc_connection.send(message)
                logger.info("Sent image data over WebRTC")
        except Exception as e:
            logger.exception(f"Error sending image data: {e}")

    async def receive_image(self, save_path):
        """
        Receive image from the server and save it.

        Args:
            save_path (str): Path where to save the received image.

        Returns:
            str: Path to the saved image file.
        """
        try:
            if self.https_connection:
                self.https_connection.request('GET', '/image')
                response = self.https_connection.getresponse()
                image_data = response.read()
                with open(save_path, 'wb') as img_file:
                    img_file.write(image_data)
                logger.info("Received image data over HTTPS")
                return save_path
            elif self.webrtc_connection:
                while True:
                    message = await self.webrtc_connection.recv()
                    data = json.loads(message)
                    if data.get("type") == "image":
                        image_data = base64.b64decode(data.get("data"))
                        with open(save_path, 'wb') as img_file:
                            img_file.write(image_data)
                        logger.info("Received image data over WebRTC")
                        return save_path
        except Exception as e:
            logger.exception(f"Error receiving image data: {e}")
            return None

    async def send_file(self, file_path):
        """
        Send a file to the server.

        Args:
            file_path (str): Path to the file to send.
        """
        try:
            with open(file_path, 'rb') as file:
                file_data = file.read()
            filename = os.path.basename(file_path)
            if self.https_connection:
                headers = {'Content-type': 'application/octet-stream', 'Filename': filename}
                self.https_connection.request('POST', '/file', body=file_data, headers=headers)
                response = self.https_connection.getresponse()
                logger.info(f"Sent file data over HTTPS, response status: {response.status}")
                response.read()
            elif self.webrtc_connection:
                encoded_file = base64.b64encode(file_data).decode('utf-8')
                message = json.dumps({"type": "file", "filename": filename, "data": encoded_file})
                await self.webrtc_connection.send(message)
                logger.info("Sent file data over WebRTC")
        except Exception as e:
            logger.exception(f"Error sending file data: {e}")

    async def receive_file(self, save_directory):
        """
        Receive a file from the server and save it.

        Args:
            save_directory (str): Directory where to save the received file.

        Returns:
            str: Path to the saved file.
        """
        try:
            if self.https_connection:
                self.https_connection.request('GET', '/file')
                response = self.https_connection.getresponse()
                headers = dict(response.getheaders())
                filename = headers.get('Filename', 'received_file')
                file_data = response.read()
                save_path = os.path.join(save_directory, filename)
                with open(save_path, 'wb') as file:
                    file.write(file_data)
                logger.info(f"Received file data over HTTPS, saved to {save_path}")
                return save_path
            elif self.webrtc_connection:
                while True:
                    message = await self.webrtc_connection.recv()
                    data = json.loads(message)
                    if data.get("type") == "file":
                        file_data = base64.b64decode(data.get("data"))
                        filename = data.get("filename", "received_file")
                        save_path = os.path.join(save_directory, filename)
                        with open(save_path, 'wb') as file:
                            file.write(file_data)
                        logger.info(f"Received file data over WebRTC, saved to {save_path}")
                        return save_path
        except Exception as e:
            logger.exception(f"Error receiving file data: {e}")
            return None

    def toggle_protocol(self):
        """
        Toggle between HTTPS and WebRTC protocols.
        """
        try:
            if self.https_connection:
                self.https_connection.close()
                self.https_connection = None
                self.is_webrtc_enabled = True
                logger.info("Switched to WebRTC protocol")
            else:
                if self.webrtc_connection:
                    asyncio.run(self.webrtc_connection.close())
                    self.webrtc_connection = None
                self.is_webrtc_enabled = False
                logger.info("Switched to HTTPS protocol")
        except Exception as e:
            logger.exception(f"Error toggling protocol: {e}")

    async def start_listening(self, url, certfile=None):
        """
        Start the communication loop with the server.

        Args:
            url (str): Server URL.
            certfile (str, optional): Path to SSL certificate file for secure WebSocket connection.
        """
        await self.connect_to_server(url, certfile=certfile)
        logger.info("Starting communication loop...")
        try:
            while True:
                # Example send/receive operations
                # Replace placeholder data with actual data handling

                # Send and receive text
                await self.send_text("Hello, server!")
                received_text = await self.receive_text()
                if received_text:
                    logger.info(f"Received text: {received_text}")

                # Send and receive audio
                # Replace with actual audio data
                audio_data = b'...'  # Placeholder for audio data
                await self.send_audio(audio_data)
                received_audio = await self.receive_audio()
                if received_audio:
                    # Process received audio data
                    pass  # Replace with actual processing

                # Send and receive video
                # Replace with actual video frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)  # Placeholder frame
                await self.send_video(frame)
                received_frame = await self.receive_video()
                if received_frame is not None:
                    # Process received video frame
                    pass  # Replace with actual processing

                # Send and receive image
                image_path = 'path_to_image.jpg'  # Replace with actual image path
                await self.send_image(image_path)
                received_image_path = await self.receive_image('received_image.jpg')
                if received_image_path:
                    # Process received image
                    pass  # Replace with actual processing

                # Send and receive file
                file_path = 'path_to_file.txt'  # Replace with actual file path
                await self.send_file(file_path)
                received_file_path = await self.receive_file('.')
                if received_file_path:
                    # Process received file
                    pass  # Replace with actual processing

                # Wait before next iteration
                await asyncio.sleep(1)
        except Exception as e:
            logger.exception(f"Error in communication loop: {e}")
        finally:
            # Clean up connections
            if self.https_connection:
                self.https_connection.close()
            if self.webrtc_connection:
                await self.webrtc_connection.close()
            logger.info("Communication loop has ended")

# Entry point
if __name__ == '__main__':
    client = Client()
    # Replace 'example.com' with the actual server URL
    # If SSL certificate is needed for WebSocket, provide the path to the certfile
    asyncio.run(client.start_listening("example.com", certfile='path_to_certfile'))
