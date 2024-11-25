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
logger = logging.getLogger("LLM-Transceiver-Client")

class Client:
    def __init__(self, signaling):
        """
        Initialize the Client with signaling mechanism and peer connection.
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
        self.received_file_path = 'received_file.bin'  # Default path

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
                logger.info(f"Received text message: {data.get('data')}")
            elif data.get("type") == "file_start":
                self.received_file_path = data.get("filename", "received_file.bin")
                self.file_buffer = bytearray()
                self.receiving_file = True
                logger.info(f"Starting file reception: {self.received_file_path}")
            elif data.get("type") == "file_end":
                with open(self.received_file_path, 'wb') as f:
                    f.write(self.file_buffer)
                self.receiving_file = False
                logger.info(f"File received and saved to {self.received_file_path}")
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
                self.media_recorder = MediaRecorder('received_media.mp4')
            self.media_recorder.addTrack(track)

    async def start(self):
        """
        Start the client: establish connection and handle media.
        """
        await self.exchange_signaling()

        # Wait for connection to be established
        await self.connected.wait()

        # Set up media
        await self.setup_media()

    async def exchange_signaling(self):
        """
        Exchange SDP and ICE candidates with the server.
        """
        await self.signaling.connect()

        # Create data channel
        self.data_channel = self.pc.createDataChannel('chat')
        self.data_channel.on("open", self.on_datachannel_open)
        self.data_channel.on("message", lambda message: asyncio.create_task(self.handle_datachannel_message(message, self.data_channel)))

        # Add local media tracks
        await self.add_local_tracks()

        # Create offer and set local description
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        # Send offer to the server
        await self.signaling.send(json.dumps({
            'sdp': self.pc.localDescription.sdp,
            'type': self.pc.localDescription.type
        }))

        # Wait for the answer
        response = await self.signaling.receive()
        answer = json.loads(response)
        await self.pc.setRemoteDescription(RTCSessionDescription(
            sdp=answer['sdp'],
            type=answer['type']
        ))

        # Exchange ICE candidates
        asyncio.create_task(self.exchange_ice_candidates())

    async def exchange_ice_candidates(self):
        """
        Exchange ICE candidates with the server.
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
        Add local media tracks from camera and microphone.
        """
        options = {'framerate': '30', 'video_size': '640x480'}
        self.media_player = MediaPlayer('/dev/video0', format='v4l2', options=options)

        if self.media_player.audio:
            self.pc.addTrack(self.media_player.audio)
        if self.media_player.video:
            self.pc.addTrack(self.media_player.video)

    async def setup_media(self):
        """
        Set up media recording.
        """
        if self.media_recorder:
            await self.media_recorder.start()

    async def on_datachannel_open(self):
        logger.info("Data channel is open")

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

    async def send_file(self, file_path):
        """
        Send a file over the data channel.
        """
        async with self.lock:
            if self.data_channel and self.data_channel.readyState == 'open':
                filename = os.path.basename(file_path)
                # Notify server of incoming file
                start_message = json.dumps({"type": "file_start", "filename": filename})
                self.data_channel.send(start_message)

                # Send file data in chunks
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(16384)
                        if not chunk:
                            break
                        self.data_channel.send(chunk)
                        await asyncio.sleep(0)  # Yield control to event loop

                # Notify server that file transmission is complete
                end_message = json.dumps({"type": "file_end"})
                self.data_channel.send(end_message)
                logger.info(f"Sent file: {file_path}")
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
        logger.info("Client has been stopped")

# Entry point
async def run_client():
    signaling = TcpSocketSignaling('localhost', 1234)
    client = Client(signaling)

    try:
        await client.start()

        # Example: Send a text message
        await client.send_text("Hello, server!")

        # Example: Send a file
        await client.send_file('path_to_file.txt')

        # Keep the client running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Client interrupted by user")
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
    finally:
        await client.stop()

if __name__ == '__main__':
    asyncio.run(run_client())
