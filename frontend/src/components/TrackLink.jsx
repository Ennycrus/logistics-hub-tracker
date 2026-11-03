/*
 * "Track" button: opens the company's tracking page for one waybill in a new tab.
 *
 * The address comes from Settings (e.g. https://.../track?waybill={waybill});
 * {waybill} is replaced by the waybill number. No address set = no button.
 * You still read the result yourself and record it with "Update".
 */
export function trackingHref(template, waybill) {
  if (!template || !waybill) return null
  return template.split('{waybill}').join(encodeURIComponent(waybill))
}

export default function TrackLink({ template, waybill }) {
  const href = trackingHref(template, waybill)
  if (!href) return null
  return (
    <a
      className="button secondary-link small-button"
      href={href}
      target="_blank"
      rel="noopener noreferrer" // the tracking site can't reach back into Hub Tracker
      title={`Open the tracking page for ${waybill}`}
    >
      Track
    </a>
  )
}
