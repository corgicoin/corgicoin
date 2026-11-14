# CorgiCoin node in a container.
#
#   docker build -f contrib/docker/Dockerfile -t corgicoind .
#   docker run -d --name corgicoin --stop-timeout 600 -v corgicoin-data:/data -p 62556:62556 corgicoind
#
# Do not publish the RPC port (62555) to the network. Run `docker exec corgicoin corgicoind -datadir=/data getblockcount`
# for a local check. --stop-timeout 600: closing the databases can take minutes, and docker's default of ten seconds
# kills the node in the middle of it.

FROM debian:12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake libboost-all-dev libssl-dev \
        libdb++-dev libminiupnpc-dev git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY . /src
WORKDIR /src/build
RUN cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF -DBUILD_TESTS=OFF && make -j"$(nproc)" corgicoind

FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libboost-system1.74.0 libboost-filesystem1.74.0 \
        libboost-thread1.74.0 libboost-program-options1.74.0 libboost-chrono1.74.0 libssl3 libdb5.3++ libminiupnpc17 \
        && rm -rf /var/lib/apt/lists/* \
    && useradd --system --home /data --shell /usr/sbin/nologin corgicoin && mkdir /data && chown corgicoin /data
COPY --from=build /src/build/corgicoind /usr/local/bin/corgicoind
USER corgicoin
VOLUME /data
EXPOSE 62556
STOPSIGNAL SIGTERM
# healthy once the RPC server answers (the cookie file in the data directory is how the client logs in)
HEALTHCHECK --interval=60s --timeout=20s --start-period=300s --retries=3 \
    CMD corgicoind -datadir=/data getblockcount || exit 1
ENTRYPOINT ["corgicoind", "-datadir=/data", "-printtoconsole", "-logtimestamps"]
