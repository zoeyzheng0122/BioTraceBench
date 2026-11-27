# Study inputs

Browse the 100 study tasks and their input manifests in the repository. The frozen inputs archive contains all 2,028 files at the paths listed on the case pages. [Study index](../data/README.md) · [Frozen inputs archive](https://github.com/zoeyzheng0122/BioTraceBench/releases/download/benchmark/BioTraceBench-frozen-inputs.tar.gz)

For all tasks, download the archive and extract the inputs into the unpacked reproduction directory.

```sh
tar -xzf BioTraceBench-frozen-inputs.tar.gz -C BioTraceBench-artifact
```

For one task, give `tar` the path from its case page.

```sh
tar -xzf BioTraceBench-frozen-inputs.tar.gz -C BioTraceBench-artifact benchmark/materials/clinical/C008
```

The reproduction archive also includes the full B008 example. [Reproduction guide](REPRODUCTION.md) · [B008](../data/B008/README.md)
