import { toast } from 'vue-toastflow'

const OPEN_LOGS_EVENT = 'app:open-logs'

const TYPE_MAP = {
  default: 'default',
  loading: 'loading',
  success: 'success',
  error: 'error',
  warning: 'warning',
  warn: 'warning',
  info: 'info',
  other: 'default',
  secondary: 'default',
  danger: 'error'
}

const TITLE_BY_TYPE = {
  default: 'Notificação',
  loading: 'Processando',
  success: 'Sucesso',
  error: 'Erro',
  warning: 'Atenção',
  info: 'Informação',
  other: 'Outro'
}

const DEFAULT_CONFIG = {
  position: 'bottom-right',
  alignment: 'left',
  progressAlignment: 'left-to-right',
  offset: '16px',
  gap: '8px',
  width: '350px',
  zIndex: 9999,
  overflowScroll: true,
  queue: true,
  duration: 5000,
  maxVisible: 5,
  preventDuplicates: false,
  order: 'newest',
  progressBar: true,
  pauseOnHover: true,
  pauseStrategy: 'resume',
  closeButton: true,
  closeOnClick: true,
  swipeToDismiss: true,
  supportHtml: true,
  showCreatedAt: true,
  buttons: {
    alignment: 'center-right',
    buttons: [
      {
        html: '<i class="pi pi-info-circle" aria-label="Abrir logs"></i>',
        onClick(ctx) {
          window.dispatchEvent(
            new CustomEvent(OPEN_LOGS_EVENT, {
              detail: {
                source: 'toastflow',
                toastId: ctx.id,
                toastType: ctx.type
              }
            })
          )
        }
      }
    ]
  }
}

function resolveInput(input) {
  if (typeof input === 'string') {
    return {
      title: '',
      description: String(input || '').trim()
    }
  }

  return {
    title: String(input?.title || '').trim(),
    description: String(input?.description || input?.message || '').trim()
  }
}

function normalizeType(type) {
  const raw = String(type || 'default').toLowerCase()
  return TYPE_MAP[raw] || 'default'
}

function resolveBaseType(type) {
  const raw = String(type || 'default').toLowerCase()
  if (raw === 'other') return 'other'
  return TYPE_MAP[raw] || 'default'
}

function buildToastConfig(type, input, options = {}) {
  const normalizedType = normalizeType(type)
  const baseType = resolveBaseType(type)
  const parsed = resolveInput(input)
  const title = parsed.title || TITLE_BY_TYPE[baseType] || TITLE_BY_TYPE.default
  const description = parsed.description

  return {
    ...DEFAULT_CONFIG,
    ...options,
    type: normalizedType,
    title,
    description
  }
}

function show(type, input, options = {}) {
  const config = buildToastConfig(type, input, options)
  return toast.show(config)
}

export function useAppToast() {
  function notify({ message = '', type = 'default', duration, title, description, ...rest } = {}) {
    return show(
      type,
      {
        title: title || '',
        description: description || message
      },
      {
        ...rest,
        ...(Number.isFinite(duration) ? { duration } : {})
      }
    )
  }

  return {
    notify,
    notifyDefault: (message, options = {}) => show('default', message, options),
    notifyLoading: (message, options = {}) => show('loading', message, options),
    notifySuccess: (message, options = {}) => show('success', message, options),
    notifyError: (message, options = {}) => show('error', message, options),
    notifyWarning: (message, options = {}) => show('warning', message, options),
    notifyInfo: (message, options = {}) => show('info', message, options),
    notifyOther: (message, options = {}) => show('other', message, options),
    dismissToast: (id) => toast.dismiss(id),
    dismissAllToasts: () => toast.dismissAll()
  }
}
