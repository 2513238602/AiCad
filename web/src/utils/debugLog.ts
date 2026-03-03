/**
 * 调试日志捕获系统
 *
 * 捕获约束应用、参数变化、生成请求/响应等关键事件，
 * 用于精准定位装配逻辑和约束传递的 bug。
 *
 * 使用: import { dlog } from '@/utils/debugLog'
 *       dlog.constraint('neck_od_mm', { min: 17, max: 19, default: 18 })
 */

export interface LogEntry {
  time: string
  category: 'constraint' | 'param' | 'generate' | 'switch' | 'derived' | 'warning'
  message: string
  data?: any
}

const MAX_ENTRIES = 500
const entries: LogEntry[] = []
let listeners: Array<() => void> = []

function ts(): string {
  const d = new Date()
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}.${d.getMilliseconds().toString().padStart(3, '0')}`
}

function add(category: LogEntry['category'], message: string, data?: any) {
  const entry: LogEntry = { time: ts(), category, message, data }
  entries.push(entry)
  if (entries.length > MAX_ENTRIES) entries.splice(0, entries.length - MAX_ENTRIES)

  // Console output with color coding
  const colors: Record<string, string> = {
    constraint: 'color:#e67e22;font-weight:bold',
    param: 'color:#2980b9',
    generate: 'color:#27ae60;font-weight:bold',
    switch: 'color:#8e44ad;font-weight:bold',
    derived: 'color:#16a085',
    warning: 'color:#c0392b;font-weight:bold',
  }
  const style = colors[category] || ''
  if (data !== undefined) {
    console.log(`%c[${category.toUpperCase()}] ${message}`, style, data)
  } else {
    console.log(`%c[${category.toUpperCase()}] ${message}`, style)
  }

  listeners.forEach((fn) => fn())
}

export const dlog = {
  /** 组件切换 */
  switch(msg: string, data?: any) {
    add('switch', msg, data)
  },

  /** 约束应用 */
  constraint(msg: string, data?: any) {
    add('constraint', msg, data)
  },

  /** 参数变化 */
  param(msg: string, data?: any) {
    add('param', msg, data)
  },

  /** 生成请求/响应 */
  generate(msg: string, data?: any) {
    add('generate', msg, data)
  },

  /** 派生参数 */
  derived(msg: string, data?: any) {
    add('derived', msg, data)
  },

  /** 警告/异常 */
  warn(msg: string, data?: any) {
    add('warning', msg, data)
  },

  /** 获取所有日志 */
  getAll(): LogEntry[] {
    return entries
  },

  /** 清空 */
  clear() {
    entries.length = 0
    listeners.forEach((fn) => fn())
  },

  /** 订阅变化 */
  subscribe(fn: () => void): () => void {
    listeners.push(fn)
    return () => {
      listeners = listeners.filter((f) => f !== fn)
    }
  },

  /** 导出为文本 */
  exportText(): string {
    return entries
      .map((e) => {
        const dataStr = e.data !== undefined ? ' ' + JSON.stringify(e.data) : ''
        return `[${e.time}][${e.category}] ${e.message}${dataStr}`
      })
      .join('\n')
  },
}
