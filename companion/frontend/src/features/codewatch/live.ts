import { reactive } from 'vue';
import type { CodewatchSource, CodewatchSourceId, CodewatchStatus } from '../../api/client';
import { loadPicked, mergeSources } from './sources';

export const codewatchLive = reactive({
  open: false,
  watching: false,
  phase: 'idle' as CodewatchStatus['phase'],
  hudPhase: 'idle' as CodewatchStatus['phase'],
  waiting: false,
  source: 'cursor' as CodewatchStatus['source'],
  picked: loadPicked() as CodewatchSourceId[],
  sources: mergeSources(undefined, loadPicked()) as CodewatchSource[],
  title: '',
  project: '',
  tool: '',
  hint: '',
  line: '',
  seq: 0,
  cursorFound: false,
  cursorHome: false,
  hooksInstalled: false,
  busy: false,
});
