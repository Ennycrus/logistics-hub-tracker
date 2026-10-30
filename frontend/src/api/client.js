/*
 * The ONE file that talks to Django.
 *
 * Every page imports functions from here instead of calling fetch() itself,
 * so login cookies, the CSRF token and error handling are done in one place.
 *
 * Errors: if Django answers with an error, these functions throw an ApiError
 * whose .message is Django's "error" text and .details its field errors.
 */

export class ApiError extends Error {
  constructor(message, status, details = {}) {
    super(message)
    this.status = status
    this.details = details
  }
}

// Read a cookie by name (Django puts the CSRF token in "csrftoken").
function getCookie(name) {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : null
}

// Methods that change data need the CSRF token.
const UNSAFE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = { Accept: 'application/json' }

  if (UNSAFE_METHODS.includes(method)) {
    headers['X-CSRFToken'] = getCookie('csrftoken') ?? ''
  }

  let payload
  if (form) {
    payload = form // FormData (file uploads): the browser sets Content-Type itself
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: payload,
      credentials: 'same-origin', // send the session cookie
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is Django running?', 0)
  }

  if (response.status === 204) return null

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    // Django's CSRF refusal is an HTML page, not JSON, so give it a clear message.
    const fallback = response.status === 403
      ? 'Security check failed. Refresh the page and try again.'
      : `Request failed (${response.status})`
    throw new ApiError(
      data?.error ?? fallback,
      response.status,
      data?.details ?? {},
    )
  }
  return data
}

// Build a query string, skipping empty values: { search: 'x', page: 2 } -> "?search=x&page=2"
function query(params = {}) {
  const clean = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return clean.length ? `?${new URLSearchParams(clean)}` : ''
}

// --- Login -----------------------------------------------------------------

export const auth = {
  csrf: () => request('/auth/csrf/'),
  me: () => request('/auth/me/'),
  login: (username, password) =>
    request('/auth/login/', { method: 'POST', body: { username, password } }),
  logout: () => request('/auth/logout/', { method: 'POST' }),
}

// --- Dropdown options ------------------------------------------------------

export const options = {
  statuses: () => request('/statuses/'),
  reasons: () => request('/reasons/'),
}

// --- Shipments -------------------------------------------------------------

export const shipments = {
  list: (params) => request(`/shipments/${query(params)}`),
  get: (id) => request(`/shipments/${id}/`),
  changeStatus: (id, change) =>
    request(`/shipments/${id}/status/`, { method: 'POST', body: change }),
  saveNotes: (id, notes) =>
    request(`/shipments/${id}/notes/`, { method: 'PATCH', body: { notes } }),
  bulkChangeStatus: (ids, change) =>
    request('/shipments/bulk-status/', { method: 'POST', body: { ...change, shipment_ids: ids } }),
}

// --- Imports ---------------------------------------------------------------

function importForm(file, extra = {}) {
  const form = new FormData()
  form.append('file', file)
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') form.append(key, value)
  })
  return form
}

export const imports = {
  preview: (file, column) =>
    request('/imports/preview/', { method: 'POST', form: importForm(file, { column }) }),
  // unknownType: 'base' | 'temu' | 'skip' for new waybills starting with neither 1 nor 3034.
  confirm: (file, reportingDate, column, unknownType) =>
    request('/imports/confirm/', {
      method: 'POST',
      form: importForm(file, { reporting_date: reportingDate, column, unknown_type: unknownType }),
    }),
  list: (params) => request(`/imports/${query(params)}`),
  get: (id) => request(`/imports/${id}/`),
}

// --- Reports ---------------------------------------------------------------
// Base and TEMU are separate reports. `type` is 'base' or 'temu' (TEMU if left out).

export const reports = {
  get: (date, type = 'temu') => request(`/reports/${date}/${query({ type })}`),
  update: (date, changes, type = 'temu') =>
    request(`/reports/${date}/${query({ type })}`, { method: 'PATCH', body: changes }),
  finalize: (date, acceptWarnings = false, type = 'temu') =>
    request(`/reports/${date}/finalize/${query({ type })}`, {
      method: 'POST',
      body: { accept_warnings: acceptWarnings },
    }),
  correct: (date, reason, type = 'temu') =>
    request(`/reports/${date}/correct/${query({ type })}`, { method: 'POST', body: { reason } }),
  // params may include type; leave it out for both types.
  history: (params) => request(`/reports/${query(params)}`),
  shipments: (date, params) => request(`/reports/${date}/shipments/${query(params)}`),
  // A plain link to this URL downloads the Excel file (the session cookie goes with it).
  downloadUrl: (date, version, type = 'temu') =>
    `/api/reports/${date}/download/${query({ type, version })}`,
  // The Monday-Saturday week containing `date`, from finalized reports.
  weekly: (date, type = 'temu') => request(`/reports/weekly/${query({ date, type })}`),
  weeklyDownloadUrl: (date, type = 'temu') => `/api/reports/weekly/download/${query({ date, type })}`,
}

// --- Settings --------------------------------------------------------------

export const settings = {
  hub: () => request('/settings/hub/'),
  updateHub: (changes) => request('/settings/hub/', { method: 'PATCH', body: changes }),

  statuses: () => request('/settings/statuses/'),
  createStatus: (status) => request('/settings/statuses/', { method: 'POST', body: status }),
  updateStatus: (id, changes) =>
    request(`/settings/statuses/${id}/`, { method: 'PATCH', body: changes }),

  reasons: () => request('/settings/reasons/'),
  createReason: (reason) => request('/settings/reasons/', { method: 'POST', body: reason }),
  updateReason: (id, changes) =>
    request(`/settings/reasons/${id}/`, { method: 'PATCH', body: changes }),
}