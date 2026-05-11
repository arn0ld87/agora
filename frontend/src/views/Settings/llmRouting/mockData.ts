// Mock-Daten für LLM Routing Pilot (Slice E)
// Backend-Verdrahtung kommt in Slice G

export type RoutingTone = 'green' | 'orange' | 'purple' | 'gray' | 'blue'

export interface StageOverrideRow {
  stage: string
  provider: string
  model: string
  effort: string
  status: string
  tone: RoutingTone
}

export interface StageStatusRow {
  stage: string
  status: string
  tone: RoutingTone
}

export interface SelectOption {
  value: string
  label: string
}

export const MOCK_ROUTING_STAGES: StageOverrideRow[] = [
  { stage: 'document_ingest',    provider: 'ollama_local',      model: 'qwen3-coder-next:cloud',   effort: 'medium', status: 'Draft',   tone: 'purple' },
  { stage: 'ontology_generation', provider: 'google',           model: 'gemini-3-flash',            effort: 'medium', status: 'Draft',   tone: 'purple' },
  { stage: 'graph_build',        provider: 'openai',            model: 'gpt-5.5-mini',              effort: 'low',    status: 'Pending', tone: 'gray'   },
  { stage: 'persona_generation', provider: 'google',            model: 'gemini-3-pro',              effort: 'high',   status: 'Draft',   tone: 'purple' },
  { stage: 'simulation_rounds',  provider: 'openai',            model: 'gpt-5.5',                   effort: 'high',   status: 'Pending', tone: 'gray'   },
  { stage: 'report_generation',  provider: 'openai',            model: 'gpt-5.5',                   effort: 'medium', status: 'Draft',   tone: 'purple' },
  { stage: 'evaluation',         provider: 'openai_compatible', model: 'deepseek-v4-flash:cloud',   effort: 'low',    status: 'Pending', tone: 'gray'   },
]

export const MOCK_STAGE_STATUS: StageStatusRow[] = [
  { stage: 'document_ingest',    status: 'Completed', tone: 'green'  },
  { stage: 'ontology_generation', status: 'Completed', tone: 'green' },
  { stage: 'graph_build',        status: 'Completed', tone: 'green'  },
  { stage: 'persona_generation', status: 'Completed', tone: 'green'  },
  { stage: 'simulation_rounds',  status: 'Running',   tone: 'orange' },
  { stage: 'report_generation',  status: 'Pending',   tone: 'gray'   },
]

export const PROVIDER_OPTIONS: SelectOption[] = [
  { value: 'openai',            label: 'OpenAI'            },
  { value: 'google',            label: 'Google'            },
  { value: 'ollama_local',      label: 'Ollama Local'      },
  { value: 'ollama_cloud',      label: 'Ollama Cloud'      },
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
]

export const MODEL_OPTIONS: SelectOption[] = [
  { value: 'gpt-5.5',                    label: 'gpt-5.5'                    },
  { value: 'gpt-5.5-mini',               label: 'gpt-5.5-mini'               },
  { value: 'gemini-3-pro',               label: 'gemini-3-pro'               },
  { value: 'gemini-3-flash',             label: 'gemini-3-flash'             },
  { value: 'qwen3-coder-next:cloud',     label: 'qwen3-coder-next:cloud'     },
  { value: 'deepseek-v4-flash:cloud',    label: 'deepseek-v4-flash:cloud'    },
]

export const EFFORT_OPTIONS: SelectOption[] = [
  { value: 'none',    label: 'None'    },
  { value: 'minimal', label: 'Minimal' },
  { value: 'low',     label: 'Low'     },
  { value: 'medium',  label: 'Medium'  },
  { value: 'high',    label: 'High'    },
]

// Initiale Global-Default-Werte (spiegelt DSA.LLMRouting)
export const INITIAL_GLOBAL_DEFAULT = {
  provider: 'openai',
  model: 'gpt-5.5',
  effort: 'medium',
  providerOptions: `{\n  "num_ctx": 32768,\n  "temperature": 0.2\n}`,
}
