import { useState } from 'react'
import { Link } from 'react-router-dom'
import { options, shipments, stockCount } from '../api/client'
import StatusEditor from '../components/StatusEditor'
import { typeLabel } from '../components/TypeSwitch'

/*
 * Stock count: scan every parcel on the shelves, then compare with the app.
 *
 *   Missing from shelves      the app says "at the hub", but it was not scanned
 *   Scanned but closed        on the shelf, but the app says delivered / left hub
 *   Scanned but not in app    on the shelf, but never imported
 *
 * Nothing is saved: fix each row (Update status, or import the missing ones),
 * then check the same scan again until everything matches.
 */
export default function StockCountPage() {
    const [file, setFile] = useState(null)
    const [pasted, setPasted] = useState('')
    const [type, setType] = useState('') // '' = both, 'temu', 'base'
    const [column, setColumn] = useState('')
    const [allColumns, setAllColumns] = useState(false)
    const [inputKey, setInputKey] = useState(0)

    const [result, setResult] = useState(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const [copied, setCopied] = useState(false)
    const [editing, setEditing] = useState(null) // { shipment, statuses, reasons }

    const pastedLines = pasted.split(/\r?\n/).filter((line) => line.trim() !== '').length

    async function check({ theFile = file, chosenColumn = column, everyColumn = allColumns, theType = type } = {}) {
        if (!theFile || busy) return
        setBusy(true)
        setError('')
        setCopied(false)
        try {
            const data = await stockCount.check(theFile, chosenColumn, everyColumn, theType)
            setResult(data)
            if (data.selected_column !== null) setColumn(String(data.selected_column))
        } catch (err) {
            setResult(null)
            setError(err.message)
        } finally {
            setBusy(false)
        }
    }

    function checkPasted() {
        if (!pastedLines) return
        const pastedFile = new File([pasted], `Shelf scan (${pastedLines} rows).txt`, { type: 'text/plain' })
        setFile(pastedFile)
        setInputKey((k) => k + 1)
        setColumn('')
        setAllColumns(false)
        check({ theFile: pastedFile, chosenColumn: '', everyColumn: false })
    }

    async function openShipment(id) {
        setError('')
        try {
            const [shipment, statuses, reasons] = await Promise.all([
                shipments.get(id), options.statuses(), options.reasons(),
            ])
            setEditing({ shipment, statuses, reasons })
        } catch (err) {
            setError(err.message)
        }
    }

    async function copyNotInApp() {
        const text = result.not_in_app.map((r) => r.waybill).join('\n')
        try {
            await navigator.clipboard.writeText(text)
            setCopied(true)
        } catch {
            setError('Could not copy. Select the waybills in the table and copy them yourself.')
        }
    }

    const ready = result && result.selected_column !== null
    const allGood = ready && !result.missing.length && !result.closed.length && !result.not_in_app.length

    return (
        <>
            <div className="card">
                <h2>Stock count</h2>
                <p className="muted">
                    Scan every parcel on the shelves, then check the scan here. The app shows what does not match.
                    Nothing is saved or changed until you update a shipment yourself.{' '}<Link to="/stock-count/checklist">No scan? Count from the pending list instead →</Link>
                </p>

                <div className="form-row">
                    <label>
                        Counting
                        <select
                            value={type}
                            onChange={(e) => {
                                setType(e.target.value)
                                if (result) check({ theType: e.target.value })
                            }}
                        >
                            <option value="">TEMU and Base</option>
                            <option value="temu">TEMU only</option>
                            <option value="base">Base only</option>
                        </select>
                    </label>
                    <label className="grow">
                        Shelf scan (.xlsx or .csv)
                        <input
                            key={inputKey}
                            type="file"
                            accept=".xlsx,.csv"
                            onChange={(e) => {
                                setFile(e.target.files[0] || null)
                                setResult(null)
                                setColumn('')
                                setAllColumns(false)
                            }}
                        />
                    </label>
                </div>

                <div className="actions">
                    <button onClick={() => check({ chosenColumn: '', everyColumn: false })} disabled={!file || busy}>
                        {busy ? 'Checking…' : 'Check scan'}
                    </button>
                </div>

                <details style={{ marginTop: 16 }} open={pasted !== ''}>
                    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Or paste from Google Sheets</summary>
                    <textarea
                        rows="6"
                        value={pasted}
                        placeholder={'303400000001\n303400000002\n...'}
                        onChange={(e) => {
                            setPasted(e.target.value)
                            setResult(null)
                        }}
                        style={{ width: '100%', fontFamily: 'monospace' }}
                    />
                    <div className="actions">
                        <span className="muted small">{pastedLines} line(s) pasted</span>
                        <button onClick={checkPasted} disabled={!pastedLines || busy}>
                            {busy ? 'Checking…' : 'Check pasted list'}
                        </button>
                    </div>
                </details>

                {error && <p className="error">{error}</p>}
            </div>

            {result && (
                <div className="card">
                    <h2>Result: {result.file_name}</h2>

                    <label className="inline-label">
                        Waybill column
                        <select
                            value={column}
                            onChange={(e) => {
                                setColumn(e.target.value)
                                check({ chosenColumn: e.target.value })
                            }}
                            disabled={busy}
                        >
                            {result.selected_column === null && <option value="">Choose the column…</option>}
                            {result.columns.map((c) => (
                                <option key={c.index} value={c.index}>{c.label}</option>
                            ))}
                        </select>
                    </label>

                    {!ready ? (
                        <p className="error">{result.message}</p>
                    ) : (
                        <>
                            <FileWarnings
                                result={result}
                                busy={busy}
                                onAllColumns={(value) => {
                                    setAllColumns(value)
                                    check({ everyColumn: value })
                                }}
                            />

                            <p className="muted">
                                {result.scanned} parcel(s) scanned
                                {result.other_type > 0 && ` (${result.other_type} ${result.shipment_type === 'temu' ? 'Base' : 'TEMU'} left out)`}
                                {' · '}{result.pending_in_app} pending in the app
                                {result.shipment_type && ` (${typeLabel(result.shipment_type)} only)`}.
                            </p>

                            <div className="stats">
                                <div className="stat"><span className="stat-value">{result.matched}</span><span className="stat-label">On shelf and pending ✓</span></div>
                                <div className="stat"><span className="stat-value">{result.missing.length}</span><span className="stat-label">Missing from shelves</span></div>
                                <div className="stat"><span className="stat-value">{result.closed.length}</span><span className="stat-label">Scanned but delivered / left hub</span></div>
                                <div className="stat"><span className="stat-value">{result.not_in_app.length}</span><span className="stat-label">Scanned but not in the app</span></div>
                            </div>

                            {allGood && <p className="success">Everything matches: the shelves and the app agree.</p>}

                            {result.missing.length > 0 && (
                                <ShipmentTable
                                    title="Missing from shelves"
                                    help="The app says these are at the hub, but they were not scanned. Find them, or update their status (e.g. delivered without an update, or initiated return)."
                                    rows={result.missing}
                                    onOpen={openShipment}
                                />
                            )}

                            {result.closed.length > 0 && (
                                <ShipmentTable
                                    title="Scanned but delivered / left hub"
                                    help="These are on the shelf, but the app says they are delivered or left the hub. Correct their status if they are really still here."
                                    rows={result.closed}
                                    onOpen={openShipment}
                                />
                            )}

                            {result.not_in_app.length > 0 && (
                                <>
                                    <h3>Scanned but not in the app</h3>
                                    <p className="muted small">
                                        These were never imported. Copy them and paste them on the{' '}
                                        <Link to="/import">Import</Link> page, with the day they arrived as the reporting date.
                                    </p>
                                    <div className="actions" style={{ justifyContent: 'flex-start' }}>
                                        <button className="small-button" onClick={copyNotInApp}>
                                            {copied ? 'Copied ✓' : `Copy ${result.not_in_app.length} waybill(s)`}
                                        </button>
                                    </div>
                                    <div className="table-wrap">
                                        <table>
                                            <thead><tr><th>Waybill</th><th>Type</th></tr></thead>
                                            <tbody>
                                                {result.not_in_app.map((r) => (
                                                    <tr key={r.waybill}>
                                                        <td className="mono">{r.waybill}</td>
                                                        <td>{r.shipment_type ? typeLabel(r.shipment_type) : '?'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </>
                            )}

                            <div className="actions">
                                <button className="secondary" onClick={() => check()} disabled={busy}>
                                    {busy ? 'Checking…' : 'Check again'}
                                </button>
                            </div>
                        </>
                    )}
                </div>
            )}

            {editing && (
                <StatusEditor
                    shipment={editing.shipment}
                    statuses={editing.statuses}
                    reasons={editing.reasons}
                    onSaved={() => {
                        setEditing(null)
                        check() // the fixed shipment moves to the right group
                    }}
                    onClose={() => setEditing(null)}
                />
            )}
        </>
    )
}

/* The same file warnings as the Import page, so no scan is missed silently. */
function FileWarnings({ result, busy, onAllColumns }) {
    return (
        <>
            {result.elsewhere?.length > 0 && (
                <div className="warning">
                    <strong>
                        {result.elsewhere.reduce((sum, c) => sum + c.count, 0)} more waybill number(s) are in other columns
                        and are NOT counted:
                    </strong>{' '}
                    {result.elsewhere.map((c) => `${c.column} (${c.count})`).join(', ')}.
                    <div className="actions" style={{ justifyContent: 'flex-start', marginTop: 8 }}>
                        <button type="button" className="small-button" onClick={() => onAllColumns(true)} disabled={busy}>
                            Count waybills from all columns
                        </button>
                    </div>
                </div>
            )}
            {result.all_columns && (
                <p className="notice">
                    Counting waybill numbers from every column.{' '}
                    <button type="button" className="link-button" onClick={() => onAllColumns(false)} disabled={busy}>
                        Only use the chosen column
                    </button>
                </p>
            )}
            {result.formulas_without_value > 0 && (
                <p className="warning">
                    {result.formulas_without_value} cell(s) contain a formula with no saved result, so they look empty.
                    Download the sheet again, or copy the column and paste it instead.
                </p>
            )}
            {result.other_sheets?.length > 0 && (
                <p className="warning">
                    This file has other sheets with data that were NOT read: {result.other_sheets.join(', ')}.
                    Only the first sheet is counted.
                </p>
            )}
        </>
    )
}

/* Missing / closed shipments, each with an Update status button. */
function ShipmentTable({ title, help, rows, onOpen }) {
    return (
        <>
            <h3>{title} ({rows.length})</h3>
            <p className="muted small">{help}</p>
            <div className="table-wrap">
                <table>
                    <thead>
                        <tr><th>Waybill</th><th>Type</th><th>Status in app</th><th>Arrived</th><th>Last update</th><th></th></tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r.shipment_id}>
                                <td className="mono">{r.waybill}</td>
                                <td>{typeLabel(r.shipment_type)}</td>
                                <td>{r.status}</td>
                                <td>{r.arrived}</td>
                                <td>
                                    {r.last_update}
                                    <span className="muted small"> ({r.days_since_update} day(s) ago)</span>
                                </td>
                                <td>
                                    <button className="secondary small-button" onClick={() => onOpen(r.shipment_id)}>
                                        Update status
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </>
    )
}