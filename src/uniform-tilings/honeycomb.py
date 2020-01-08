"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
3d hyperbolic honeycombs in Poincaré's ball model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Note for ideal and hyperideal cases you must make
sure (p, q, r) are ordered so that (p, q) form a
finite spherical polyhedra, this is due to our
construction of the reflection mirrors. For example
(6, 3, 3) won't work, but (3, 3, 6) does.
"""
from functools import partial
from itertools import combinations
import numpy as np
import tqdm
import helpers
from coxeter import CoxeterGroup


def vround(v):
    """Convert a numpy 1d array to a tuple for hashing.
    """
    return tuple(np.round(v, 8))


def centroid(points):
    """Compute the centroid of a list of points.
    """
    mid = helpers.normalize(np.sum(points, axis=0))
    return vround(mid)


class Cell(object):

    """A cell is a uniform polyhedra (or a "room") in the 3d tiling.
    """

    def __init__(self, cox_mat, v0, active, reflections):
        self.cox_mat = cox_mat
        self.v0 = v0
        self.active = active
        self.reflections = reflections
        self.G = CoxeterGroup(cox_mat)

        self.vertices_coords = []
        self.num_vertices = None
        self.edge_coords = []
        self.num_edges = None

    def build_geometry(self):
        self.G.init()
        self.words = tuple(self.G.traverse())
        self.get_vertices()
        self.get_edges()
        return self

    def transform(self, word, v):
        for w in reversed(word):
            v = self.reflections[w](v)
        return vround(v)

    def project(self, v):
        return helpers.project_poincare(v)

    def get_vertices(self):
        for word in self.words:
            v = self.transform(word, self.v0)
            if v not in self.vertices_coords:
                self.vertices_coords.append(v)
        self.num_vertices = len(self.vertices_coords)

    def get_edges(self):
        """
        An edge is uniquely determined by the coordinates of its
        middle point. Here I simply use a set to maintain the middle
        points of known edges and avoid duplicates.
        """
        edgehash = set()
        for i, active in enumerate(self.active):
            if active:
                for word in self.words:
                    p1 = self.transform(word, self.v0)
                    p2 = self.transform(word + (i,), self.v0)
                    q = centroid((p1, p2))
                    if q not in edgehash:
                        self.edge_coords.append((p1, p2))
                        edgehash.add(q)
        self.num_edges = len(self.edge_coords)


class Honeycomb(object):

    def __init__(self, coxeter_diagram, init_dist):
        if len(coxeter_diagram) != 6 or len(init_dist) != 4:
            raise ValueError("Invalid input dimension")

        # Coxeter matrix and its rank
        self.cox_mat = helpers.make_symmetry_matrix(coxeter_diagram)
        self.rank = len(self.cox_mat)

        # generators of the symmetry group
        self.gens = tuple(range(self.rank))

        # symmetry group of this tiling
        self.G = CoxeterGroup(self.cox_mat)

        # a mirror is active iff the initial point is not on it
        self.active = tuple(bool(x) for x in init_dist)

        # reflection mirrors
        self.mirrors = self.get_mirrors(coxeter_diagram)

        # reflections (possibly affine) about the mirrors
        self.reflections = self.get_reflections()

        # coordinates of the initial point
        self.init_v = self.get_init_point(init_dist)

        self.fundamental_cells = self.get_fundamental_cells()

        self.edge_hash_set = set()

        self.num_vertices = 0
        self.num_edges = 0

    def get_reflections(self):
        def reflect(v, normal):
            return v - 2 * np.dot(v, normal) * normal

        return [partial(reflect, normal=n) for n in self.mirrors]

    def transform(self, word, v):
        for w in reversed(word):
            v = self.reflections[w](v)
        return vround(v)

    def project(self, v):
        return helpers.project_poincare(v)

    def get_init_point(self, init_dist):
        return helpers.get_point_from_distance(self.mirrors, init_dist)

    def get_mirrors(self, coxeter_diagram):
        return helpers.get_hyperbolic_honeycomb_mirrors(coxeter_diagram)

    def get_fundamental_cells(self):
        """
        Generate the fundamental cells of the tiling, these cells
        are centered at the vertices of the fundamental tetrahedron
        and are generated by reflecting the initial point about
        the three mirrors meeting at each vertex.
        """
        result = {}
        for triple in combinations(self.gens, 3):
            cox_mat = self.cox_mat[np.ix_(triple, triple)]
            refs = [self.reflections[k] for k in triple]
            active = [self.active[k] for k in triple]
            if not helpers.is_degenerate(cox_mat, active):
                C = Cell(cox_mat, self.init_v, active, refs).build_geometry()
                result[triple] = C
        return result

    def is_new_edge(self, edge):
        mid = centroid(edge)
        if mid not in self.edge_hash_set:
            self.edge_hash_set.add(mid)
            return True
        return False

    def collect_fundamental_cell_edges(self):
        result = []
        for C in self.fundamental_cells.values():
            for edge in C.edge_coords:
                if self.is_new_edge(edge):
                    result.append(edge)
        return result

    def export_edge(self, fobj, p1, p2):
        """Export the data of an edge to POV-Ray .inc file."""
        fobj.write("HyperbolicEdge({}, {})\n".format(
            helpers.pov_vector(p1),
            helpers.pov_vector(p2)))

    def generate_povray_data(self, depth=100, maxcount=50000,
                             filename="./povray/honeycomb-data.inc",
                             eye=(0, 0, 0.5),
                             lookat=(0, 0, 0)):
        self.G.init()
        self.word_generator = partial(self.G.traverse, depth=depth, maxcount=maxcount)
        init_edges = self.collect_fundamental_cell_edges()
        bar = tqdm.tqdm(desc="processing edges", total=maxcount)
        vertices = set()
        eye = np.array(eye)
        lookat = np.array(lookat)
        viewdir = helpers.normalize(lookat - eye)

        def add_new_edge(edge):
            p1 = self.project(edge[0])
            p2 = self.project(edge[1])
            if np.dot(p1 - eye, viewdir) > 0.5 or np.dot(p2 - eye, viewdir) > 0.5:
                self.export_edge(f, p1, p2)
                self.num_edges += 1
                for v in [p1, p2]:
                    v = vround(v)
                    if v not in vertices:
                        vertices.add(v)
                        self.num_vertices += 1

        with open(filename, "w") as f:
            f.write("#declare camera_loc = {};\n".format(helpers.pov_vector(eye)))
            f.write("#declare lookat = {};\n".format(helpers.pov_vector(lookat)))
            for edge in init_edges:
                add_new_edge(edge)

            for word in self.word_generator():
                for edge in init_edges:
                    edge = [self.transform(word, v) for v in edge]
                    if self.is_new_edge(edge):
                        add_new_edge(edge)

                bar.update(1)
            bar.close()
            verts = "#declare num_vertices = {};\n"
            verts_coords = "#declare vertices = array[{}]{{{}}};\n"
            print("{} vertices and {} edges generated".format(self.num_vertices, self.num_edges))
            f.write(verts.format(self.num_vertices))
            f.write(verts_coords.format(self.num_vertices, helpers.pov_vector_list(vertices)))
