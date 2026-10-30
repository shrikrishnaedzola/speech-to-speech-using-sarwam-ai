// Browser side of a live call: microphone -> WebRTC -> our backend (Pipecat),
// and the agent's voice back into an <audio> element.
//
// Plain RTCPeerConnection, no SDK: we gather all ICE candidates first, then
// send one offer to /api/webrtc/offer and apply the answer.

import { useRef, useState } from "react";
import { api } from "../api";

function waitForIceGathering(pc, timeoutMs = 3000) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => pc.iceGatheringState === "complete" && done();
    pc.addEventListener("icegatheringstatechange", check);
    setTimeout(done, timeoutMs); // don't wait forever on slow STUN
  });
}

export function useVoiceCall() {
  const pcRef = useRef(null);
  const streamRef = useRef(null);
  const audioRef = useRef(null);
  const [muted, setMuted] = useState(false);
  const [connected, setConnected] = useState(false);

  async function connect(session) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    streamRef.current = stream;

    const iceServers = (session.ice_servers || []).map((item) => {
      if (typeof item === "string") return { urls: item };
      return item;
    });
    const pc = new RTCPeerConnection({ iceServers });
    pcRef.current = pc;

    // Audio must be the first transceiver (the server expects it at index 0).
    pc.addTransceiver(stream.getAudioTracks()[0], { direction: "sendrecv" });
    pc.createDataChannel("events"); // unused, but avoids a server-side warning

    pc.ontrack = (e) => {
      if (!audioRef.current) audioRef.current = new Audio();
      audioRef.current.srcObject = e.streams[0] ?? new MediaStream([e.track]);
      audioRef.current.play().catch(() => {});
    };
    pc.onconnectionstatechange = () => setConnected(pc.connectionState === "connected");

    await pc.setLocalDescription(await pc.createOffer());
    await waitForIceGathering(pc);
    const answer = await api.sendOffer(session.webrtc_offer_url, {
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
    });
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
  }

  function disconnect() {
    pcRef.current?.close();
    pcRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (audioRef.current) audioRef.current.srcObject = null;
    setConnected(false);
    setMuted(false);
  }

  function toggleMute() {
    const track = streamRef.current?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setMuted(!track.enabled);
  }

  return { connect, disconnect, toggleMute, muted, connected };
}
