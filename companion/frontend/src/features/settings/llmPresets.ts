// LLM 服务商预设（全部 OpenAI 兼容协议），选择后自动填接口地址和推荐模型
export const LLM_PRESETS: Record<string, { base: string; model: string }> = {
  bailian: { base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  volcano: { base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-1-6-250615' },
  volcano_character: { base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-character-260628' },
  deepseek: { base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  moonshot: { base: 'https://api.moonshot.cn/v1', model: 'kimi-k2-turbo-preview' },
  zhipu: { base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.5-flash' },
  openai: { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  gemini: { base: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.0-flash' },
  openrouter: { base: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
  anthropic: { base: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-5' },
  groq: { base: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
  mistral: { base: 'https://api.mistral.ai/v1', model: 'mistral-small-latest' },
  xai: { base: 'https://api.x.ai/v1', model: 'grok-3' },
  together: { base: 'https://api.together.xyz/v1', model: 'meta-llama/Llama-3.3-70B-Instruct-Turbo' },
  fireworks: { base: 'https://api.fireworks.ai/inference/v1', model: 'accounts/fireworks/models/llama-v3p3-70b-instruct' },
  nvidia: { base: 'https://integrate.api.nvidia.com/v1', model: 'meta/llama-3.3-70b-instruct' },
  cerebras: { base: 'https://api.cerebras.ai/v1', model: 'llama-3.3-70b' },
  perplexity: { base: 'https://api.perplexity.ai', model: 'sonar' },
  novita: { base: 'https://api.novita.ai/v3/openai', model: 'deepseek/deepseek-v3' },
  comet: { base: 'https://api.cometapi.com/v1', model: 'gpt-4o-mini' },
  featherless: { base: 'https://api.featherless.ai/v1', model: 'meta-llama/Llama-3.3-70B-Instruct' },
  aihubmix: { base: 'https://aihubmix.com/v1', model: 'gpt-4o-mini' },
  ai302: { base: 'https://api.302.ai/v1', model: 'gpt-4o-mini' },
  siliconflow: { base: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
  stepfun: { base: 'https://api.stepfun.com/v1', model: 'step-2-mini' },
  baichuan: { base: 'https://api.baichuan-ai.com/v1', model: 'Baichuan4-Turbo' },
  minimax: { base: 'https://api.minimaxi.com/v1', model: 'MiniMax-M2' },
  modelscope: { base: 'https://api-inference.modelscope.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct' },
  hunyuan: { base: 'https://api.hunyuan.cloud.tencent.com/v1', model: 'hunyuan-turbos-latest' },
  mimo: { base: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-v2.6-flash' },
  mimo_pro: { base: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-v2.6-pro' },
  moonshot_intl: { base: 'https://api.moonshot.ai/v1', model: 'kimi-k2-turbo-preview' },
  qwen_intl: { base: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  ollama: { base: 'http://127.0.0.1:11434/v1', model: 'llama3.2' },
  vllm: { base: 'http://127.0.0.1:8000/v1', model: 'default' },
  sglang: { base: 'http://127.0.0.1:30000/v1', model: 'default' },
  player2: { base: 'http://127.0.0.1:4315/v1', model: 'player2' },
  minicpm: { base: 'https://api.modelbest.cn/v1', model: 'MiniCPM-O-4.5-9B' },
};
export function inferLlmPreset(baseUrl: string, model: string): string {
  const base = baseUrl.trim().replace(/\/+$/, '').toLowerCase();
  const candidates = Object.entries(LLM_PRESETS).filter(([, preset]) => {
    return base === preset.base.toLowerCase() || base.startsWith(preset.base.toLowerCase() + '/');
  });
  return (candidates.find(([, preset]) => model === preset.model) || candidates[0])?.[0] || 'custom';
}
