Today's mix spans from practical embedding compression tricks to synthetic datasets pushing multimodal boundaries.

## **Main picks**

### [PCA before truncation makes non-Matryoshka embeddings compressible: results on BGE-M3](https://www.reddit.com/r/MachineLearning/comments/1sgt7ol/p_pca_before_truncation_makes_nonmatryoshka/)
Simple but clever approach to compress non-Matryoshka embeddings by rotating into PCA space before truncating dimensions. The results are striking — going from 0.333 to 0.933 cosine similarity at 128d on BGE-M3. This could be immediately useful for your RAG work where you need smaller embeddings but don't have Matryoshka-trained models. Worth testing on your current embedding pipeline.
[reddit]

### [When Numbers Speak: Aligning Textual Numerals and Visual Instances in Text-to-Video Diffusion Models](http://arxiv.org/abs/2604.08546v1)
NUMINA tackles the surprisingly hard problem of getting text-to-video models to generate the right number of objects ("three cats" actually producing three cats). Their training-free approach uses attention head selection to identify counting failures, then guides regeneration through cross-attention modulation. Solid improvements across model sizes, and the attention mechanism insights could translate to other multimodal alignment problems you're working on.
[arxiv]

### [FIT: A Large-Scale Dataset for Fit-Aware Virtual Try-On](http://arxiv.org/abs/2604.08526v1)
Finally, someone's tackling garment fit in virtual try-on instead of just appearance transfer. They've built a 1.13M image dataset with precise body and garment measurements, using physics simulation for realistic draping then a re-texturing pipeline to make it photorealistic. The synthetic-to-real pipeline here is noteworthy — could inspire approaches for other domains where you need precise physical constraints in generated data.
[arxiv]

### [ETCH-X: Robustify Expressive Body Fitting to Clothed Humans with Composable Datasets](http://arxiv.org/abs/2604.08548v1)
Upgrades SMPL body fitting with a clever "undress then dense fit" approach that separates clothing dynamics from body pose estimation. The modular training on different data sources (CLOTH3D, AMASS, InterHand2.6M) is smart — lets them scale robustness without needing massive unified datasets. Could be relevant if you're working with any 3D human pose or embodied AI projects.
[arxiv]

## **Also worth a look**

- [Gaming anti-cheat system falsely banning disabled player](https://www.reddit.com/r/ArcRaiders/comments/1sfxx0a/suffered_two_bans_before_embark_unbanned_me_for/) — interesting case study in how AI bias detection can fail edge cases
- Multiple duplicate entries in feed suggest some content aggregation issues in the system
- [Random comic](https://www.reddit.com/r/comics/comments/1sfbjeq/swords_cut_your_losses/) somehow made it through the ML filter