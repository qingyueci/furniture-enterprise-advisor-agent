import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ConsultationData, ConversationMessage } from '../api/agent'
import AgentMessage from './AgentMessage.vue'

function message(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: 'message-1',
    role: 'ASSISTANT',
    content: '测试回答',
    task_type: 'CONSULTATION',
    structured_data: null,
    citations: [],
    tool_summary: [],
    warnings: [],
    created_at: '2026-09-16T00:00:00Z',
    ...overrides,
  }
}

function degradedConsultation(): ConsultationData {
  return {
    kind: 'CONSULTATION',
    answer_format: 'CANDIDATES',
    retrieval_queries: [],
    degraded: true,
    pending_slots: [],
    conversation_topic: null,
    session_conditions: [],
  }
}

describe('AgentMessage warnings', () => {
  it('renders stable Chinese text for routing and generation fallbacks', () => {
    const wrapper = mount(AgentMessage, {
      props: { message: message({ warnings: ['ROUTING_FALLBACK', 'GENERATION_FALLBACK'] }) },
    })

    expect(wrapper.text()).toContain('本轮采用确定性路由，请结合回答与引用核验')
    expect(wrapper.text()).toContain('本轮生成已降级为受控结果，请优先核验引用')
  })

  it('deduplicates warning codes and uses one generic text for an unknown code', () => {
    const wrapper = mount(AgentMessage, {
      props: { message: message({ warnings: ['ROUTING_FALLBACK', 'ROUTING_FALLBACK', 'PRIVATE_REASON'] }) },
    })

    expect(wrapper.findAll('.message-warning')).toHaveLength(2)
    expect(wrapper.text().match(/本轮采用确定性路由/g)).toHaveLength(1)
    expect(wrapper.text()).toContain('本轮存在状态提醒，请核验回答和引用')
    expect(wrapper.text()).not.toContain('PRIVATE_REASON')
  })

  it('does not render an empty warning container for ordinary or user messages', async () => {
    const wrapper = mount(AgentMessage, { props: { message: message() } })
    expect(wrapper.find('.message-warnings').exists()).toBe(false)

    await wrapper.setProps({
      message: message({ role: 'USER', task_type: null, warnings: ['ROUTING_FALLBACK'] }),
    })
    expect(wrapper.find('.message-warnings').exists()).toBe(false)
  })

  it('does not duplicate the degraded badge when generation fallback is visible', () => {
    const wrapper = mount(AgentMessage, {
      props: {
        message: message({
          structured_data: degradedConsultation(),
          warnings: ['GENERATION_FALLBACK'],
        }),
      },
    })

    expect(wrapper.text()).toContain('本轮生成已降级为受控结果')
    expect(wrapper.text()).not.toContain('已降级 · 请核验摘录')
  })

  it('keeps the legacy degraded badge when no generation warning exists', () => {
    const wrapper = mount(AgentMessage, {
      props: { message: message({ structured_data: degradedConsultation() }) },
    })

    expect(wrapper.text()).toContain('已降级 · 请核验摘录')
  })

  it('renders a warning from a history-shaped message without transient request state', () => {
    const historyMessage = JSON.parse(JSON.stringify(message({
      id: 'persisted-message',
      warnings: ['ROUTING_FALLBACK'],
    }))) as ConversationMessage

    const wrapper = mount(AgentMessage, { props: { message: historyMessage } })
    expect(wrapper.find('.message-warnings').exists()).toBe(true)
    expect(wrapper.text()).toContain('本轮采用确定性路由')
  })
})
