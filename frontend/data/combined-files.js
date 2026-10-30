export function createCombinedRepository(regionalRepository) {
    let groupsPromise;
    const placements = new Map();

    function getGroups() {
        if (!groupsPromise) {
            groupsPromise = regionalRepository.listPngs().then(
                paths => {
                    const groups = new Map();

                    for (const path of paths) {
                        const name = path.split("/").at(-1);

                        if (!groups.has(name)) groups.set(name, []);
                        groups.get(name).push(path);
                    }

                    return groups;
                },
                error => {
                    groupsPromise = undefined;
                    throw error;
                },
            );
        }

        return groupsPromise;
    }

    function getPlacement(path) {
        if (!placements.has(path)) {
            const pending = regionalRepository.getPlacement(path).catch(error => {
                placements.delete(path);
                throw error;
            });

            placements.set(path, pending);
        }

        return placements.get(path);
    }

    async function getPlacements(name) {
        const groups = await getGroups();
        const paths = groups.get(name);

        if (!paths) {
            throw new Error(`Unknown PNG group: ${name}`);
        }

        return Promise.all(
            paths.map(async path => ({
                path,
                ...await getPlacement(path),
            })),
        );
    }

    function contains(bounds, longitude, latitude) {
        const [west, south, east, north] = bounds;
        const wrappedLongitude = ((longitude + 180) % 360 + 360) % 360 - 180;

        return (
            wrappedLongitude >= west &&
            wrappedLongitude <= east &&
            latitude >= south &&
            latitude <= north
        );
    }

    return {
        async listPngs() {
            return [...(await getGroups()).keys()];
        },

        getPlacements,

        getSummaryReader(name) {
            return {
                async readPoint(longitude, latitude) {
                    const items = await getPlacements(name);

                    for (const { path, bounds } of items) {
                        if (!contains(bounds, longitude, latitude)) continue;

                        const point = await regionalRepository
                            .getSummaryReader(path)
                            .readPoint(longitude, latitude);

                        if (point) return point;
                    }

                    return null;
                },
            };
        },
    };
}