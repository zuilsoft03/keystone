// The Decision form (P3-80; design §3.3): the form's rows, what it must have before it saves, and the Client Decision it saves.
export const CATEGORIES = ['Material', 'Finish', 'Colour', 'Fixture', 'Equipment', 'Layout', 'Other']
// A decision is final in these states: the form shows it read-only (client_decision.py FINAL).
export const FINAL = ['Decided', 'Withdrawn', 'Changed']

export const blankOption = () => ({ name: '', option_key: '', label: '', file: '', cost_difference: '', time_difference: '', supplier: '', description: '' })
export const blankDecision = () => ({ title: '', category: 'Material', description: '', currency: '', amounts_include_vat: 0, options: [blankOption(), blankOption()], recommended: -1 })

export function fromDoc(doc) {
  const options = (doc.options || []).map((o) => ({ ...blankOption(), ...o, cost_difference: o.cost_difference ?? '', time_difference: o.time_difference ?? '' }))
  return {
    name: doc.name, status: doc.status, modified: doc.modified, title: doc.title || '', category: doc.category || 'Other', description: doc.description || '',
    currency: doc.currency || '', amounts_include_vat: doc.amounts_include_vat ? 1 : 0, options,
    recommended: options.findIndex((o) => o.option_key && o.option_key === doc.recommended_option),
  }
}

// The words keys of what is missing (the form shows them as sentences); none means it may save.
export function decisionErrors(d) {
  const errors = []
  if (!d.title?.trim()) errors.push('dec_err_title')
  if (!d.options?.length) errors.push('dec_err_options')
  else if (d.options.some((o) => !o.label?.trim())) errors.push('dec_err_label')
  return errors
}

export const priced = (d) => d.options.some((o) => Number(o.cost_difference) || Number(o.time_difference))

// The document to save. A saved option keeps its row name (and so its key); the recommended one is set after the save
// because a new option's key is the server's (see recommendedKey).
export function toDoc(d, project) {
  return {
    project, title: d.title.trim(), category: d.category, description: d.description, currency: d.currency.trim(), amounts_include_vat: d.amounts_include_vat ? 1 : 0,
    options: d.options.map((o) => ({
      ...(o.name ? { name: o.name } : {}), label: o.label.trim(), file: o.file, description: o.description, supplier: o.supplier,
      cost_difference: Number(o.cost_difference) || 0, time_difference: Math.trunc(Number(o.time_difference)) || 0,
    })),
  }
}

// The key of the option the team recommends, from the saved document's rows (the same order as the form's).
export const recommendedKey = (saved, index) => (index >= 0 ? saved.options?.[index]?.option_key || '' : '')

// "Make the variation" shows on a decided Decision whose options change price or time; the server checks the rest.
export const canMakeVariation = (d) => d.status === 'Decided' && priced(d)
