export const flattenTaxonomy = (nodes = []) =>
  nodes.flatMap((node) => [node, ...flattenTaxonomy(node.children || [])]);

export const leafTaxonomy = (nodes = []) =>
  flattenTaxonomy(nodes).filter((node) => node.kind === "category" && !(node.children || []).length);

export const findTaxonomyNode = (nodes = [], slug) =>
  flattenTaxonomy(nodes).find((node) => node.slug === slug) || null;

export const taxonomySections = (root) => {
  const items = (root?.children || []).filter((node) => node.kind === "category");
  return items.length ? [{ items }] : [];
};

export const taxonomyLabel = (node, locale, pickLocalized) =>
  pickLocalized(node?.translations, locale) || node?.slug || "";
