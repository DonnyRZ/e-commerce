export const flattenTaxonomy = (nodes = []) =>
  nodes.flatMap((node) => [node, ...flattenTaxonomy(node.children || [])]);

export const leafTaxonomy = (nodes = []) =>
  flattenTaxonomy(nodes).filter((node) => node.kind === "category" && !(node.children || []).length);

export const findTaxonomyNode = (nodes = [], slug) =>
  flattenTaxonomy(nodes).find((node) => node.slug === slug) || null;

export const taxonomySections = (root) => {
  const children = root?.children || [];
  const direct = children.filter((node) => node.kind !== "group");
  const grouped = children
    .filter((node) => node.kind === "group")
    .map((group) => ({ group, items: group.children || [] }));
  return [
    ...(direct.length ? [{ group: null, items: direct }] : []),
    ...grouped,
  ];
};

export const taxonomyLabel = (node, locale, pickLocalized) =>
  pickLocalized(node?.translations, locale) || node?.slug || "";
