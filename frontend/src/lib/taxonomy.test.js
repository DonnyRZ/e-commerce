import { findTaxonomyNode, flattenTaxonomy, leafTaxonomy, taxonomySections } from "./taxonomy";

const tree = [
  {
    id: "batik",
    kind: "department",
    slug: "batik",
    children: [
      {
        id: "batik-women",
        kind: "category",
        slug: "gamis-batik",
        children: [],
      },
      { id: "tunik", kind: "category", slug: "tunik-batik", children: [] },
      { id: "hijab", kind: "category", slug: "hijab-pashmina-batik", children: [] },
    ],
  },
];

describe("taxonomy helpers", () => {
  test("flattens nodes and keeps only selectable leaf categories", () => {
    expect(flattenTaxonomy(tree).map((node) => node.slug)).toEqual([
      "batik",
      "gamis-batik",
      "tunik-batik",
      "hijab-pashmina-batik",
    ]);
    expect(leafTaxonomy(tree).map((node) => node.slug)).toEqual([
      "gamis-batik",
      "tunik-batik",
      "hijab-pashmina-batik",
    ]);
  });

  test("finds direct product categories", () => {
    expect(findTaxonomyNode(tree, "tunik-batik").id).toBe("tunik");
    expect(taxonomySections(tree[0])).toEqual([
      { items: tree[0].children },
    ]);
  });
});
