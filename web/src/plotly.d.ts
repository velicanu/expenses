// plotly.js-basic-dist-min ships no types; this is the part the app uses.
declare module "plotly.js-basic-dist-min" {
  interface PlotlyStatic {
    react(root: HTMLElement, data: unknown[], layout?: unknown, config?: unknown): Promise<unknown>;
    purge(root: HTMLElement): void;
  }
  const Plotly: PlotlyStatic;
  export default Plotly;
}
