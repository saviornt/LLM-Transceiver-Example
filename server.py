import asyncio
import logging
import os
import ssl
import json
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceServer,
    RTCDataChannel
)
from aiortc.contrib.signaling import TcpSocketSignaling
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from aiortc.mediastreams import MediaStreamError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LLM-Transceiver-Server")

class Server:
    def __init__(self, signaling):
        """
        Initialize the Server with signaling mechanism and peer connection.
        """
        self.signaling = signaling
        self.pc = RTCPeerConnection()
        self.media_player = None
        self.media_recorder = None
        self.data_channel = None
        self.connected = asyncio.Event()
        self.lock = asyncio.Lock()
        self.file_buffer = bytearray()
        self.receiving_file = False
        self.received_file_path = 'server_received_file.bin'  # Default path

        # Set up event handlers
        self.pc.on("iceconnectionstatechange", self.on_ice_connection_state_change)
        self.pc.on("datachannel", self.on_datachannel)
        self.pc.on("track", self.on_track)

    async def on_ice_connection_state_change(self):
        logger.info(f"ICE connection state is {self.pc.iceConnectionState}")
        if self.pc.iceConnectionState == 'connected':
            self.connected.set()
        elif self.pc.iceConnectionState == 'failed':
            await self.pc.close()
            self.connected.clear()

    def on_datachannel(self, channel: RTCDataChannel):
        logger.info(f"Data channel received: {channel.label}")

        @channel.on("message")
        def on_message(message):
            asyncio.create_task(self.handle_datachannel_message(message, channel))

    async def handle_datachannel_message(self, message, channel):
        if isinstance(message, str):
            data = json.loads(message)
            if data.get("type") == "text":
                text = data.get("data")
                logger.info(f"Received text message: {text}")

                # Process the text with LLM (placeholder for actual LLM processing)
                response_text = self.process_text_with_llm(text)
                await self.send_text(response_text)
            elif data.get("type") == "file_start":
                self.received_file_path = data.get("filename", "server_received_file.bin")
                self.file_buffer = bytearray()
                self.receiving_file = True
                logger.info(f"Starting file reception: {self.received_file_path}")
            elif data.get("type") == "file_end":
                with open(self.received_file_path, 'wb') as f:
                    f.write(self.file_buffer)
                self.receiving_file = False
                logger.info(f"File received and saved to {self.received_file_path}")

                # Optionally process the file with LLM
                response_text = self.process_file_with_llm(self.received_file_path)
                await self.send_text(response_text)
        else:
            # Binary data (file chunks)
            if self.receiving_file:
                self.file_buffer.extend(message)
                logger.debug(f"Received file chunk of size {len(message)} bytes")
            else:
                logger.warning("Received binary data but not in file reception mode")

    def on_track(self, track: MediaStreamTrack):
        logger.info(f"Track received: {track.kind}")

        if track.kind == "audio" or track.kind == "video":
            if not self.media_recorder:
                self.media_recorder = MediaRecorder('server_received_media.mp4')
            self.media_recorder.addTrack(track)

    async def start(self):
        """
        Start the server: accept connection and handle media.
        """
        await self.exchange_signaling()

        # Wait for connection to be established
        await self.connected.wait()

        # Set up media
        await self.setup_media()

    async def exchange_signaling(self):
        """
        Exchange SDP and ICE candidates with the client.
        """
        await self.signaling.connect()

        # Wait for the offer from the client
        request = await self.signaling.receive()
        offer = json.loads(request)
        await self.pc.setRemoteDescription(RTCSessionDescription(
            sdp=offer['sdp'],
            type=offer['type']
        ))

        # Create answer and set local description
        await self.add_local_tracks()
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        # Send answer back to the client
        await self.signaling.send(json.dumps({
            'sdp': self.pc.localDescription.sdp,
            'type': self.pc.localDescription.type
        }))

        # Exchange ICE candidates
        asyncio.create_task(self.exchange_ice_candidates())

    async def exchange_ice_candidates(self):
        """
        Exchange ICE candidates with the client.
        """
        async def send_ice_candidates():
            while True:
                candidate = await self.pc.sctp.transport.getRemoteCandidate()
                if candidate is None:
                    break
                await self.signaling.send(json.dumps({
                    'candidate': candidate.to_sdp(),
                    'sdpMid': candidate.sdpMid,
                    'sdpMLineIndex': candidate.sdpMLineIndex
                }))

        asyncio.create_task(send_ice_candidates())

        while True:
            message = await self.signaling.receive()
            if message is None:
                break
            data = json.loads(message)
            candidate = RTCIceCandidate(
                sdpMid=data['sdpMid'],
                sdpMLineIndex=data['sdpMLineIndex'],
                candidate=data['candidate']
            )
            await self.pc.addIceCandidate(candidate)

    async def add_local_tracks(self):
        """
        Add local media tracks (if any) to the peer connection.
        """
        # Optionally, you can add media tracks to send audio/video to the client
        pass  # For now, the server does not send media tracks

    async def setup_media(self):
        """
        Set up media recording.
        """
        if self.media_recorder:
            await self.media_recorder.start()

    async def send_text(self, message):
        """
        Send a text message over the data channel.
        """
        async with self.lock:
            if self.data_channel and self.data_channel.readyState == 'open':
                data = json.dumps({"type": "text", "data": message})
                self.data_channel.send(data)
                logger.info(f"Sent text message: {message}")
            else:
                logger.warning("Data channel is not open")

    async def stop(self):
        """
        Stop media processing and close the connection.
        """
        if self.media_recorder:
            await self.media_recorder.stop()
        if self.media_player:
            await self.media_player.stop()
        if self.pc:
            await self.pc.close()
        if self.signaling:
            await self.signaling.close()
        logger.info("Server has been stopped")

    def process_text_with_llm(self, text):
        """
        Process the received text with the LLM.

        Args:
            text (str): The received text message.

        Returns:
            str: The response text from the LLM.
        """
        # Placeholder for LLM processing
        # Replace this with actual LLM inference code
        response = f"LLM response to: {text}"
        return response

    def process_file_with_llm(self, file_path):
        """
        Process the received file with the LLM.

        Args:
            file_path (str): Path to the received file.

        Returns:
            str: The response text from the LLM after processing the file.
        """
        # Placeholder for LLM processing
        # Replace this with actual LLM inference code
        response = f"LLM processed file: {file_path}"
        return response

# Entry point
async def run_server():
    signaling = TcpSocketSignaling('localhost', 1234)
    server = Server(signaling)

    try:
        await server.start()

        # Keep the server running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
    finally:
        await server.stop()

if __name__ == '__main__':
    asyncio.run(run_server())
