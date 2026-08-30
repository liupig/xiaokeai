/* Classic worker: no import/export. MediaPipe WASM glue uses importScripts. */
if (typeof document === 'undefined') {
  self.document = {
    createElement: function (tag) {
      if (tag === 'canvas') return new OffscreenCanvas(1, 1);
      return {};
    },
  };
}

var exports = {};
var module = { exports: exports };
var BASE = self.location.href.replace(/[^/]+$/, '');
importScripts(BASE + 'mediapipe/vision_bundle.js');

var FilesetResolver = module.exports.FilesetResolver;
var HolisticLandmarker = module.exports.HolisticLandmarker;

var WASM = BASE + 'mediapipe/wasm';
var MODEL =
  'https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/1/holistic_landmarker.task';

var landmarker = null;

function post(msg) {
  self.postMessage(msg);
}

function emit(result, mediaTs, aspect, inferenceMs) {
  post({
    type: 'result',
    mediaTs: mediaTs,
    result: {
      inferenceMs: inferenceMs,
      poseWorldLandmarks: result.poseWorldLandmarks,
      leftHandWorldLandmarks: result.leftHandWorldLandmarks,
      rightHandWorldLandmarks: result.rightHandWorldLandmarks,
      faceLandmarks: result.faceLandmarks,
      poseLandmarks: result.poseLandmarks,
      imageAspect: aspect,
    },
  });
}

function init() {
  return FilesetResolver.forVisionTasks(WASM).then(function (vision) {
    var opts = {
      baseOptions: { modelAssetPath: MODEL, delegate: 'GPU' },
      minPosePresenceConfidence: 0.7,
      minPoseDetectionConfidence: 0.7,
      minFaceDetectionConfidence: 0.4,
      minHandLandmarksConfidence: 0.95,
      runningMode: 'VIDEO',
    };
    return HolisticLandmarker.createFromOptions(vision, opts).catch(function (gpuError) {
      console.warn('Holistic GPU 失败，改用 CPU', gpuError);
      opts.baseOptions.delegate = 'CPU';
      return HolisticLandmarker.createFromOptions(vision, opts);
    });
  }).then(function (lm) {
    landmarker = lm;
    try {
      var canvas = new OffscreenCanvas(256, 256);
      var ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#808080';
        ctx.fillRect(0, 0, 256, 256);
      }
      return new Promise(function (resolve) {
        landmarker.detectForVideo(canvas, performance.now(), function () { resolve(); });
      });
    } catch (e) {
      console.warn('MediaPipe 预热失败（可忽略）', e);
    }
  }).then(function () {
    post({ type: 'ready' });
  });
}

self.onmessage = function (e) {
  var msg = e.data;
  var p = Promise.resolve();
  try {
    if (msg.type === 'init') {
      p = init();
    } else if (msg.type === 'reset') {
      if (landmarker) p = landmarker.setOptions({ runningMode: 'VIDEO' });
    } else if (msg.type === 'video') {
      if (landmarker) {
        var aspect = msg.bitmap.width / Math.max(1, msg.bitmap.height);
        var t0 = performance.now();
        landmarker.detectForVideo(msg.bitmap, msg.ts, function (result) {
          emit(result, msg.mediaTs, aspect, performance.now() - t0);
        });
      }
      msg.bitmap.close();
    }
  } catch (err) {
    post({ type: 'error', message: err && err.message ? err.message : String(err) });
    return;
  }
  p.catch(function (err) {
    post({ type: 'error', message: err && err.message ? err.message : String(err) });
  });
};
