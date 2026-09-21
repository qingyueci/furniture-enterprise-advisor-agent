export interface UsageCapability {
  name: string
  description: string
  examples: string[]
}

export interface GuideItem {
  name: string
  description: string
}

export const confirmedStableCapabilities: UsageCapability[] = [
  {
    name: '资料内的证据化咨询',
    description: '依据本地导入且当前角色可见的资料回答材料、规则和选型问题，并在回答中给出引用。',
    examples: [
      '潮湿环境选择柜体材料需要核对什么？',
      '现有资料对这项规则的适用条件怎么说明？',
    ],
  },
  {
    name: '报价与规则口径核对',
    description: '区分单价、单位、包含项、增项、有效期、地区、税运和合同边界。',
    examples: [
      '这条报价按什么单位，包含哪些项目？',
      '这项交付规则有哪些适用条件？',
    ],
  },
]

export const candidateCapabilities: UsageCapability[] = [
  {
    name: '多轮关键条件承接',
    description: '承接当前会话中的对象、数值、单位和显式修改；重要决策前仍应复核最新条件。',
    examples: [],
  },
  {
    name: '双产品比较与条件式推荐',
    description: '按已知字段比较两个候选，并明确未被资料覆盖的条件。',
    examples: [],
  },
]

export const usageConditions: GuideItem[] = [
  { name: '场景选材', description: '说明使用空间、环境和最关注的条件。' },
  { name: '报价核对', description: '提供报价对象、来源或记录编号。' },
  { name: '产品比较', description: '提供具体候选，或先整理比较维度。' },
  { name: '售后与交付', description: '尽量提供品牌、型号、购买日期和合同凭证。' },
]

export const materialBoundaries: GuideItem[] = [
  { name: '产品资料', description: '只支持已导入资料中明确记录的字段，缺失内容需要继续核实。' },
  { name: '演示报价', description: '公开仓库的 DEMO 数据仅用于功能演示，不代表商业报价。' },
  { name: '产品名称与系列', description: '名称和系列不能替代具体型号、规格及检测附件。' },
  { name: '平台观点', description: '观点材料不能替代合同、检测或官方资料。' },
]

export const verifiedIssues: GuideItem[] = [
  { name: '证据相关性', description: '证据与当前对象不一致时停止采用，并提示继续核对。' },
  { name: '条件继承', description: '条件变更后应确认回答采用最新条件。' },
  { name: '资料边界', description: '未检索到证据不等于资料库中不存在该内容。' },
]

export const capabilitySnapshot = {
  version: 'PUBLIC-1',
  status: '功能演示',
  note: '公开代码版不包含内部评测统计；能力以本地导入资料和实际测试结果为准。',
}
