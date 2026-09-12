import { findTaxonomyNode, flattenTaxonomy, leafTaxonomy, taxonomySections } from "./taxonomy";

const tree = [
  {
    id: "batik",
    kind: "department",
    slug: "batik",
    children: [
      {
        id: "batik-women",
        kind: "group",
        slug: "batik-wanita-muslimah",
        children: [
          { id: "gamis", kind: "category", slug: "gamis-batik", children: [] },
          { id: "tunik", kind: "category", slug: "tunik-batik", children: [] },
        ],
      },
      { id: "sarung", kind: "category", slug: "sarung-batik", children: [] },
    ],
  },
];

describe("taxonomy helpers", () => {
  test("flattens nodes and keeps only selectable leaf categories", () => {
    expect(flattenTaxonomy(tree).map((node) => node.slug)).toEqual([
      "batik",
      "batik-wanita-muslimah",
      "gamis-batik",
      "tunik-batik",
      "sarung-batik",
    ]);
    expect(leafTaxonomy(tree).map((node) => node.slug)).toEqual([
      "gamis-batik",
      "tunik-batik",
      "sarung-batik",
    ]);
  });

  test("finds nested nodes and groups direct children separately", () => {
    expect(findTaxonomyNode(tree, "tunik-batik").id).toBe("tunik");
    expect(taxonomySections(tree[0])).toEqual([
      { group: null, items: [tree[0].children[1]] },
      {
        group: tree[0].children[0],
        items: tree[0].children[0].children,
      },
    ]);
  });
});
