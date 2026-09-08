import './App.css'

const routes = [
  {
    name: 'KEEP',
    level: 'L0',
    description: 'La foto è già utilizzabile. Nessuna trasformazione.',
  },
  {
    name: 'LIGHT POLISH',
    level: 'L1',
    description: 'Correzione leggera con Cloudinary e_improve.',
  },
  {
    name: 'GPT IMAGE RECOVERY',
    level: 'L4',
    description:
      'Recovery avanzato con GPT Image e conferma umana obbligatoria.',
  },
  {
    name: 'RETAKE',
    level: '—',
    description:
      'La foto è troppo ambigua o compromessa per essere migliorata in sicurezza.',
  },
]

const benchmarks = [
  {
    comparison: 'L1 vs L0',
    result: '14 / 9 / 7',
    detail: '14 vittorie · 9 pareggi · 7 sconfitte',
    verdict: 'KEEP L1',
  },
  {
    comparison: 'L4 vs L0',
    result: '28 / 1 / 1',
    detail: '28 vittorie · 1 pareggio · 1 sconfitta',
    verdict: 'KEEP L4',
  },
  {
    comparison: 'L2 vs L1',
    result: '5 / 13 / 12',
    detail: '5 vittorie L2 · 13 pareggi · 12 vittorie L1',
    verdict: 'DROP L2',
  },
  {
    comparison: 'L3 vs L4',
    result: '0 / 3 / 27',
    detail: '0 vittorie L3 · 3 pareggi · 27 vittorie L4',
    verdict: 'DROP L3',
  },
]

const operational = [
  {
    label: 'L1 median latency',
    value: '3.94 s',
  },
  {
    label: 'L1 p95 latency',
    value: '4.90 s',
  },
  {
    label: 'L4 median latency',
    value: '42.10 s',
  },
  {
    label: 'L4 p95 latency',
    value: '45.63 s',
  },
  {
    label: 'L4 average cost',
    value: '$0.0526',
  },
  {
    label: 'L4 vs L1 latency',
    value: '~10.7×',
  },
]

function App() {
  return (
    <main className="lab-page">
      <section className="hero">
        <p className="eyebrow">Photo Quality Lab</p>

        <h1>Safe Enhancement & Recoverability Routing</h1>

        <p className="hero-copy">
          Experimental dashboard for the photo-quality routing system.
          Benchmarking, safety validation and final production policy.
        </p>

        <div className="hero-tags">
          <span>30-photo golden set</span>
          <span>Diagnosis v5</span>
          <span>Routing v3</span>
          <span>Human-in-the-loop</span>
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <p className="section-kicker">Final architecture</p>
          <h2>Four productive outcomes</h2>
        </div>

        <div className="route-grid">
          {routes.map((route) => (
            <article className="route-card" key={route.name}>
              <div className="route-top">
                <span className="route-level">{route.level}</span>
                <span className="route-name">{route.name}</span>
              </div>

              <p>{route.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <p className="section-kicker">Human quality review</p>
          <h2>Benchmark results</h2>
        </div>

        <div className="benchmark-table">
          <div className="benchmark-row benchmark-header">
            <span>Comparison</span>
            <span>Result</span>
            <span>Decision</span>
          </div>

          {benchmarks.map((benchmark) => (
            <div className="benchmark-row" key={benchmark.comparison}>
              <div>
                <strong>{benchmark.comparison}</strong>
                <p>{benchmark.detail}</p>
              </div>

              <strong className="benchmark-result">
                {benchmark.result}
              </strong>

              <span
                className={`verdict ${
                  benchmark.verdict.startsWith('DROP')
                    ? 'verdict-drop'
                    : 'verdict-keep'
                }`}
              >
                {benchmark.verdict}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <p className="section-kicker">Safety</p>
          <h2>Fidelity & recoverability</h2>
        </div>

        <div className="safety-grid">
          <article className="metric-card">
            <span className="metric-value">8 / 30</span>
            <h3>L4 material alterations</h3>
            <p>
              Human review identified eight outputs with material changes.
              Six originated from ambiguity already present in the input.
            </p>
          </article>

          <article className="metric-card">
            <span className="metric-value">83.3%</span>
            <h3>Candidate gate recall</h3>
            <p>
              The frozen RETAKE gate catches five of six known ambiguity
              failures while keeping false positives limited.
            </p>
          </article>

          <article className="metric-card">
            <span className="metric-value">83.3%</span>
            <h3>Candidate gate precision</h3>
            <p>
              RETAKE is deliberately conservative: an unnecessary retake is
              preferable to a plausible but false property representation.
            </p>
          </article>

          <article className="metric-card">
            <span className="metric-value">95.5%</span>
            <h3>Specificity</h3>
            <p>
              Most safe images remain recoverable rather than being blocked by
              the gate.
            </p>
          </article>
        </div>

        <div className="policy-card">
          <p className="policy-label">Frozen candidate gate</p>

          <code>
            verifiability_risk = high AND resolution_risk != none → RETAKE
          </code>

          <p>
            Recoverable L4 outputs require explicit human confirmation before
            being considered approved.
          </p>
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <p className="section-kicker">Operational benchmark</p>
          <h2>Latency & cost</h2>
        </div>

        <div className="operational-grid">
          {operational.map((item) => (
            <article className="operational-card" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>

        <p className="operational-note">
          L4 is intentionally reserved for cases that need substantial
          recovery. The golden set was deliberately degraded to stress the
          system and is not intended to represent the expected production route
          distribution.
        </p>
      </section>

      <section className="section">
        <div className="section-heading">
          <p className="section-kicker">Production policy</p>
          <h2>Final routing logic</h2>
        </div>

        <div className="routing-flow">
          <div>
            <span>1</span>
            <strong>Impossible / unsafe recovery</strong>
            <p>Monochrome or candidate-gate failure → RETAKE</p>
          </div>

          <div>
            <span>2</span>
            <strong>Serious information loss</strong>
            <p>Blur, compression, noise or resolution loss → L4</p>
          </div>

          <div>
            <span>3</span>
            <strong>Significant exposure problem</strong>
            <p>Medium/high under- or overexposure → L4</p>
          </div>

          <div>
            <span>4</span>
            <strong>Light photographic issue</strong>
            <p>Low exposure issue or color triage → L1</p>
          </div>

          <div>
            <span>5</span>
            <strong>No relevant issue</strong>
            <p>Input is preserved unchanged → KEEP</p>
          </div>
        </div>
      </section>
    </main>
  )
}

export default App