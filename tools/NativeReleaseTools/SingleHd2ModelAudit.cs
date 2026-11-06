using System.Numerics;
using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;

internal static class SingleHd2ModelAudit
{
    internal static async Task RunAsync(string[] args)
    {
        var folder=Path.GetFullPath(args[1]);
        var units=0;var vertices=0;var matrices=0;var outsideBounds=0;
        var allowStaleBounds=args.Length>3 && args[3]=="--allow-stale-bounds";double maxInverseError=0,maxFkError=0;
        var minimum=new[]{double.PositiveInfinity,double.PositiveInfinity,double.PositiveInfinity};
        var maximum=new[]{double.NegativeInfinity,double.NegativeInfinity,double.NegativeInfinity};
        float[] Values(Matrix4x4 m)=>[m.M11,m.M12,m.M13,m.M14,m.M21,m.M22,m.M23,m.M24,
            m.M31,m.M32,m.M33,m.M34,m.M41,m.M42,m.M43,m.M44];
        Matrix4x4 Matrix(IReadOnlyList<float> v)=>new(v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],
            v[8],v[9],v[10],v[11],v[12],v[13],v[14],v[15]);
        foreach(var patch in Directory.GetFiles(folder,"*.patch_*").Where(p=>int.TryParse(p.Split('_').Last(),out _)))
        foreach(var entry in (await new PatchTocScanner().ScanEntriesAsync(patch)).Where(e=>e.AssetKey.TypeId==PatchUnitMeshReader.UnitTypeId))
        {
            var payload=await new PatchEntryPayloadReader().ReadPayloadAsync(entry);
            var model=new UnitMeshReader().Read(payload.TocData,payload.GpuResourceData);units++;
            var info=model.TransformInfo;
            var relevant=new HashSet<int>();
            foreach(var palette in model.BoneInfos)
            {
                if(palette.BoneMatrices.Count!=palette.RealIndices.Count)throw new InvalidDataException("Incomplete inverse bind palette.");
                for(var i=0;i<palette.RealIndices.Count;i++)
                {
                    var index=(int)palette.RealIndices[i];
                    var inverse=Enumerable.Range(0,16).Select(k=>BitConverter.ToSingle(palette.BoneMatrices[i],k*4)).ToArray();
                    var identity=Values(Matrix(inverse)*Matrix(info.Matrices[index].Values));
                    for(var k=0;k<16;k++)maxInverseError=Math.Max(maxInverseError,Math.Abs(identity[k]-(k%5==0?1:0)));
                    matrices++;
                    var cursor=index;
                    while(relevant.Add(cursor))
                    {
                        var parent=info.Entries[cursor].ParentIndex;
                        if(parent==cursor)break;
                        if(parent>=info.NameHashes.Count)throw new InvalidDataException("Invalid skin ancestor.");
                        cursor=parent;
                    }
                }
            }
            foreach(var i in relevant)
            {
                var l=info.LocalTransforms[i];var r=l.Rotation;
                var local=Matrix(new[]{r[0]*l.Scale[0],r[1]*l.Scale[0],r[2]*l.Scale[0],0,
                    r[3]*l.Scale[1],r[4]*l.Scale[1],r[5]*l.Scale[1],0,
                    r[6]*l.Scale[2],r[7]*l.Scale[2],r[8]*l.Scale[2],0,l.Position[0],l.Position[1],l.Position[2],1});
                var parent=info.Entries[i].ParentIndex;
                var composed=Values(parent==i?local:local*Matrix(info.Matrices[parent].Values));
                for(var k=0;k<16;k++)maxFkError=Math.Max(maxFkError,Math.Abs(composed[k]-info.Matrices[i].Values[k]));
            }
            foreach(var mesh in model.Meshes.Where(m=>m.LodIndex>=0))
            {
                var meshWorld=Values(Matrix(info.Matrices[(int)mesh.TransformIndex].Values));
                if(meshWorld.Where((v,i)=>Math.Abs(v-(i%5==0?1:0))>1e-6).Any())throw new InvalidDataException("Nonidentity mesh transform.");
                var raw=model.RawMeshData.Single(m=>m.MeshInfoIndex==mesh.Index);
                if(!UnitGeometryFactsBuilder.HasRenderableGeometry(raw))continue;
                var bounds=mesh.CullingBounds.Values;
                foreach(var vertex in raw.Vertices)
                {
                    var point=vertex.Components.Single(c=>c.Type==0).FloatValues;vertices++;
                    for(var k=0;k<3;k++)
                    {
                        if(!float.IsFinite(point[k]))throw new InvalidDataException("Nonfinite vertex.");
                        if(point[k]<bounds[k]-1e-4 || point[k]>bounds[k+3]+1e-4)
                        {
                            outsideBounds++;
                            if(!allowStaleBounds)throw new InvalidDataException("Vertex outside serialized culling bounds.");
                        }
                        minimum[k]=Math.Min(minimum[k],point[k]);maximum[k]=Math.Max(maximum[k],point[k]);
                    }
                }
            }
        }
        if(units!=7 || vertices==0 || matrices==0 || maxInverseError>1e-4 || maxFkError>1e-4)
            throw new InvalidDataException($"Invalid skin bind: units={units}, inverse={maxInverseError}, FK={maxFkError}");
        var report=new {status="PASS",units,vertices,skinMatrices=matrices,maxInverseBindError=maxInverseError,
            maxFkError,outsideBounds,minimum,maximum,height=maximum[2]-minimum[2],gameTested=false};
        var json=JsonSerializer.Serialize(report,new JsonSerializerOptions{WriteIndented=true});
        File.WriteAllText(args[2],json);Console.WriteLine(json);
    }
}
