export default function Legal({ title, updated, sections }: { title: string; updated: string; sections: Array<[string, string]> }) {
  return (
    <section className="bg-white">
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h1 className="text-4xl font-bold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-2 text-sm text-slate-500">Last updated {updated}</p>
        <div className="mt-10 space-y-8">
          {sections.map(([h, body], i) => (
            <div key={h}>
              <h2 className="text-lg font-semibold text-slate-900">{i + 1}. {h}</h2>
              <p className="mt-2 whitespace-pre-line leading-relaxed text-slate-700">{body}</p>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
