// cytoscape-fcose ships no TypeScript declarations. `cytoscape.use(fcose)`
// only needs the module to exist (its runtime shape is opaque to us), so an
// ambient `any` declaration is sufficient and honest.
declare module "cytoscape-fcose";