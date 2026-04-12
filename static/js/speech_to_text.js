(function () {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const isSupported = Boolean(
    navigator.mediaDevices &&
      navigator.mediaDevices.getUserMedia &&
      AudioContextClass
  );
  const speechButtons = Array.from(document.querySelectorAll("[data-speech-button]"));
  let warmupPromise = null;
  let isWarm = false;

  function getCookie(name) {
    const cookieValue = document.cookie
      .split(";")
      .map(function (item) {
        return item.trim();
      })
      .find(function (item) {
        return item.indexOf(name + "=") === 0;
      });
    if (!cookieValue) return "";
    return decodeURIComponent(cookieValue.slice(name.length + 1));
  }

  function findField(button) {
    const container = button.closest("[data-speech-field]");
    if (!container) return null;
    return container.querySelector("[data-speech-input]") || container.querySelector("input, textarea");
  }

  function floatTo16BitPCM(float32Array) {
    const pcm = new Int16Array(float32Array.length);
    for (let index = 0; index < float32Array.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, float32Array[index]));
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm;
  }

  function mergeBuffers(buffers) {
    const totalLength = buffers.reduce(function (sum, current) {
      return sum + current.length;
    }, 0);
    const merged = new Float32Array(totalLength);
    let offset = 0;
    buffers.forEach(function (buffer) {
      merged.set(buffer, offset);
      offset += buffer.length;
    });
    return merged;
  }

  function encodeWav(samples, sampleRate) {
    const pcmSamples = floatTo16BitPCM(samples);
    const dataLength = pcmSamples.length * 2;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    function writeString(offset, value) {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
      }
    }

    writeString(0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, dataLength, true);

    pcmSamples.forEach(function (sample, index) {
      view.setInt16(44 + index * 2, sample, true);
    });

    return new Blob([buffer], { type: "audio/wav" });
  }

  function appendRecognizedText(field, text) {
    const trimmedText = (text || "").trim();
    if (!trimmedText) return;
    const currentValue = field.value || "";
    const separator = currentValue.trim() ? (field.tagName === "TEXTAREA" ? "\n" : " ") : "";
    field.value = currentValue + separator + trimmedText;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.focus();
  }

  async function parseJsonResponse(response, fallbackMessage) {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = (await response.text()).replace(/\s+/g, " ").trim();
      const snippet = text.slice(0, 120);
      throw new Error(
        snippet
          ? "Сервер вернул HTML вместо JSON: " + snippet
          : fallbackMessage
      );
    }
    return response.json();
  }

  function setWarmupLoading(isLoading) {
    speechButtons.forEach(function (button) {
      if (!isSupported || (activeSession && activeSession.button === button)) {
        return;
      }
      button.disabled = isLoading;
      button.classList.toggle("is-loading", isLoading);
      if (isLoading) {
        button.title = "Подготавливаем распознавание речи...";
      } else {
        button.removeAttribute("title");
      }
    });
  }

  async function warmupSpeech() {
    if (!isSupported || !speechButtons.length || isWarm) {
      return;
    }
    if (!warmupPromise) {
      setWarmupLoading(true);
      warmupPromise = fetch("/speech/warmup/", {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then(async function (response) {
          const data = await parseJsonResponse(
            response,
            "Не удалось подготовить распознавание речи."
          );
          if (!response.ok) {
            throw new Error(
              data.error || "Не удалось подготовить распознавание речи."
            );
          }
          isWarm = true;
          return data;
        })
        .catch(function (error) {
          warmupPromise = null;
          throw error;
        })
        .finally(function () {
          setWarmupLoading(false);
        });
    }
    return warmupPromise;
  }

  let activeSession = null;

  async function stopRecording(button) {
    if (!activeSession || activeSession.button !== button) return;

    const session = activeSession;
    activeSession = null;
    button.disabled = true;
    button.classList.remove("is-recording");
    button.classList.add("is-loading");

    session.processor.disconnect();
    session.source.disconnect();
    session.stream.getTracks().forEach(function (track) {
      track.stop();
    });
    await session.audioContext.close();

    try {
      const wavBlob = encodeWav(mergeBuffers(session.buffers), session.sampleRate);
      const payload = new FormData();
      payload.append("audio", new File([wavBlob], "speech.wav", { type: "audio/wav" }));

      const response = await fetch("/speech/transcribe/", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: payload,
      });
      const data = await parseJsonResponse(
        response,
        "Не удалось распознать аудио."
      );
      if (!response.ok) {
        throw new Error(data.error || "Не удалось распознать аудио.");
      }
      appendRecognizedText(session.field, data.text || "");
    } catch (error) {
      window.alert(error.message || "Не удалось распознать аудио.");
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
    }
  }

  async function startRecording(button) {
    const field = findField(button);
    if (!field) {
      return;
    }

    if (activeSession && activeSession.button !== button) {
      await stopRecording(activeSession.button);
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = new AudioContextClass({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const buffers = [];

    processor.onaudioprocess = function (event) {
      const channelData = event.inputBuffer.getChannelData(0);
      buffers.push(new Float32Array(channelData));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    activeSession = {
      button: button,
      field: field,
      stream: stream,
      source: source,
      processor: processor,
      buffers: buffers,
      audioContext: audioContext,
      sampleRate: audioContext.sampleRate || 16000,
    };
    button.classList.add("is-recording");
  }

  speechButtons.forEach(function (button) {
    if (!isSupported) {
      button.disabled = true;
      button.title = "Запись с микрофона не поддерживается в этом браузере.";
    }
  });

  warmupSpeech().catch(function () {
    // Allow a retry when the user clicks the button later.
  });

  document.addEventListener("click", async function (event) {
    const button = event.target.closest("[data-speech-button]");
    if (!button) {
      return;
    }
    if (!isSupported || button.disabled) {
      return;
    }

    try {
      if (activeSession && activeSession.button === button) {
        await stopRecording(button);
      } else {
        await warmupSpeech();
        await startRecording(button);
      }
    } catch (error) {
      button.classList.remove("is-recording", "is-loading");
      button.disabled = false;
      window.alert(error.message || "Не удалось включить микрофон.");
    }
  });
})();
