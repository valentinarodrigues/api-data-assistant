import { useState } from 'react'

const API_COLORS = {
  orders:    'bg-blue-900/50 text-blue-300',
  products:  'bg-emerald-900/50 text-emerald-300',
  customers: 'bg-amber-900/50 text-amber-300',
}

export default function FieldSidebar({ fields }) {
  const [query, setQuery] = useState('')

  const filtered = fields.filter(f => {
    if (!query) return true
    const q = query.toLowerCase()
    return (
      f.field_path?.toLowerCase().includes(q) ||
      f.display_name?.toLowerCase().includes(q) ||
      f.description?.toLowerCase().includes(q) ||
      f.api_name?.toLowerCase().includes(q)
    )
  })

  return (
    <aside className="w-72 flex-shrink-0 flex flex-col border-r border-slate-800 bg-[#0b0d14]">
      <div className="p-4 border-b border-slate-800">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          All API Fields
        </p>
        <input
          type="search"
          placeholder="Search fields…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="w-full rounded-lg bg-slate-800 text-slate-200 placeholder-slate-500
                     text-sm px-3 py-2 outline-none focus:ring-1 focus:ring-violet-500"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="text-slate-500 text-sm p-4">No fields match.</p>
        ) : (
          filtered.map((f, i) => <FieldRow key={i} field={f} />)
        )}
      </div>

      <div className="p-3 border-t border-slate-800 text-slate-600 text-xs text-center">
        {filtered.length} / {fields.length} fields
      </div>
    </aside>
  )
}

function FieldRow({ field }) {
  const required   = field.required === 'Yes'
  const apiColor   = API_COLORS[field.api_id] ?? 'bg-slate-800 text-slate-400'

  return (
    <div className="px-4 py-3 border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors">
      <div className="flex items-center gap-1.5 flex-wrap mb-1">
        <code className="text-violet-400 text-xs font-mono">{field.field_path}</code>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${apiColor}`}>
          {field.api_name}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          required ? 'bg-violet-900/50 text-violet-300' : 'bg-slate-800 text-slate-500'
        }`}>
          {required ? 'required' : 'optional'}
        </span>
      </div>
      <p className="text-slate-400 text-xs leading-snug">{field.description}</p>
      {field.example && (
        <p className="text-slate-600 text-xs mt-1">e.g. {field.example}</p>
      )}
    </div>
  )
}
